import pika
import json
import frappe
import os
from metactical.custom_scripts.utils.orders_api import receive_rmq_data
from metactical.custom_scripts.utils.metactical_utils import post_to_rocket_chat

def process_message(message):
    # Retrieve the RabbitMQ Mapping doctype
    frappe.log_error(title="new_message", message=message)
    mappings = frappe.get_all("RabbitMQ Mapping", fields=["message_type", "method_call"])
    
    # Process the message based on its type
    message_type = message.get("message_type")
    matched = False
    for mapping in mappings:
        if mapping.message_type == message_type:
            matched = True
            try:
                # Dynamically call the mapped method
                method_to_call = frappe.get_attr(mapping.method_call)
                method_to_call(message)
            except Exception as e:
                # Log the error in ERPNext logs
                error_message = f"Error processing RMQ message: {message}\nError: {str(e)}"
                frappe.log_error(error_message, "RabbitMQ Message Processing Error")
                post_to_rocket_chat([], f"Error processing RMQ message: {str(e)}", rmq=True)

    if not matched:
        error_message = f"No mapping found for message type: {message_type}"
        frappe.log_error(error_message, "RabbitMQ Message Processing Error")

# Callback function for RabbitMQ
def callback(ch, method, properties, body):
    try:
        # Decode the message (assuming JSON format)
        message = json.loads(body)

        # Post the message to Frappe
        # frappe.enqueue(job_name="process_rfq_message", method=process_message, queue="default", message=message, at_front=True)
        process_message(message)
        
        # Acknowledge the message
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        # If there's an error, you can choose to not acknowledge
        ch.basic_nack(delivery_tag=method.delivery_tag)

# Function to start the RabbitMQ consumer
def start_consumer(rounds=0):
    try:
        # # Find the position of the target substring
        target = "frappe-bench"
        current_path =  os.path.abspath(__file__)

        pos = current_path.find(target)
        if pos != -1:
            result = current_path[:pos]+target+"/sites"  # If target found, return the string up to the target
        else:
            result = current_path  # If target not found, return the whole string

        # Change the current working directory to the site directory
        os.chdir(result)
        frappe.init(site='erp.metactical.com')
        frappe.connect()

        # RabbitMQ connection parameters
        config = frappe.get_doc('RabbitMQ Config')

        username = config.username
        password = config.password
        server_ip = config.server_ip
        rabbitmq_queue = config.queue_name

        # Set up RabbitMQ connection
        credentials = pika.PlainCredentials(username, password)
        connection_params = pika.ConnectionParameters(server_ip, credentials=credentials)
        connection = pika.BlockingConnection(connection_params)
        channel = connection.channel()

        # Declare the queue (make sure it exists)
        channel.queue_declare(queue=rabbitmq_queue, durable=True)

        # Set up the consumer
        channel.basic_consume(queue=rabbitmq_queue, on_message_callback=callback)

        post_to_rocket_chat([], "RabbitMQ receiver is now running.", rmq=True)
        channel.start_consuming()

    except pika.exceptions.StreamLostError as e:
        error_message = f"RMQ Stream connection lost: {str(e)}"
        frappe.log_error(error_message, "RabbitMQ Consumption Error")
        post_to_rocket_chat([], error_message, rmq=True)
        
        # Attempt to reconnect with a delay
        post_to_rocket_chat([], "RabbitMQ receiver is now running.", rmq=True)
        start_consumer()
    except Exception as e:
        error_message = f"Error during RMQ message consumption: {str(e)}"
        post_to_rocket_chat([], error_message, rmq=True)
        frappe.log_error(error_message, "RabbitMQ Consumption Error")

        # Attempt to reconnect with a delay
        if rounds < 5:
            start_consumer(rounds=rounds+1)

if __name__ == "__main__":
    start_consumer()
