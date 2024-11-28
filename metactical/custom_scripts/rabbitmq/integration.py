import frappe
import pika
import json

connection = None
channel = None

def subscribe_to_rabbitmq():
    global connection, channel

    # Retrieve the RabbitMQ Config doctype
    config = frappe.get_doc("RabbitMQ Config")
    
    # Validate required fields
    required_fields = ['server_ip', 'username', 'password', 'queue_name']
    missing_fields = [field for field in required_fields if not getattr(config, field, None)]
    if missing_fields:
        error_message = f"Missing required fields in RabbitMQ Config: {', '.join(missing_fields)}"
        frappe.log_error(error_message, "RabbitMQ Configuration Error")
        return

    # Validate mappings
    mappings = frappe.get_all("RabbitMQ Mapping", fields=["message_type", "method_call"])
    if not mappings:
        error_message = "No mappings found in RabbitMQ Mapping"
        frappe.log_error(error_message, "RabbitMQ Configuration Error")
        return

    # Stop any existing subscription
    stop_subscription()

    # Extract server details
    server_ip = config.server_ip
    username = config.username
    password = config.password
    queue_name = config.queue_name

    print(server_ip)
    print(username)
    print(password)
    print(queue_name)

    connect(server_ip, username, password, queue_name)

def connect(server_ip, username, password, queue_name):
    global connection, channel
    try:
        # Set up RabbitMQ connection
        credentials = pika.PlainCredentials(username, password)
        connection_params = pika.ConnectionParameters(server_ip, credentials=credentials)
        connection = pika.BlockingConnection(connection_params)
        channel = connection.channel()
        
        # Declare the queue
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Define the callback function to process messages
        def callback(ch, method, properties, body):
            message = json.loads(body)
            process_message(message)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        
        # Start consuming messages
        channel.basic_consume(queue=queue_name, on_message_callback=callback)
        channel.start_consuming()
    except pika.exceptions.StreamLostError as e:
        error_message = f"Stream connection lost: {str(e)}"
        frappe.log_error(error_message, "RabbitMQ Consumption Error")
        # Attempt to reconnect with a delay
        frappe.enqueue('metactical.custom_scripts.rabbitmq.integration.connect', queue='long' , timeout=None, server_ip=server_ip, username=username, password=password, queue_name=queue_name, enqueue_after_commit=True)
    except Exception as e:
        error_message = f"Error during message consumption: {str(e)}"
        frappe.log_error(error_message, "RabbitMQ Consumption Error")
        # Attempt to reconnect with a delay
        frappe.enqueue('metactical.custom_scripts.rabbitmq.integration.connect', queue='long',  timeout=None, server_ip=server_ip, username=username, password=password, queue_name=queue_name, enqueue_after_commit=True)

def stop_subscription():
    global connection, channel
    try:
        if channel and channel.is_open:
            channel.close()
        if connection and connection.is_open:
            connection.close()
    except Exception as e:
        error_message = f"Error stopping RabbitMQ subscription: {str(e)}"
        frappe.log_error(error_message, "RabbitMQ Stop Subscription Error")
    finally:
        connection = None
        channel = None

def process_message(message):
    # Retrieve the RabbitMQ Mapping doctype
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
                error_message = f"Error processing message: {message}\nError: {str(e)}"
                frappe.log_error(error_message, "RabbitMQ Message Processing Error")
    if not matched:
        error_message = f"No match found for message_type: {message_type}\nMessage: {message}"
        frappe.log_error(error_message, "RabbitMQ Message Processing Error")

@frappe.whitelist()
def printmessage(message):
    error_message = f"Got message: {message}\n"
    frappe.log_error(error_message, "Success")

def config_change_handler(doc, method):
    # This function will be called whenever the RabbitMQ Config is updated
    stop_existing_jobs()
    frappe.enqueue('metactical.custom_scripts.rabbitmq.integration.subscribe_to_rabbitmq', queue='long' , timeout=None)

def stop_existing_jobs():
    # Stop existing background jobs
    columns = frappe.db.get_table_columns('Scheduled Job Log')
    method_column_exists = 'method' in columns
    if method_column_exists:
        jobs = frappe.get_all('Scheduled Job Log', filters={'status': 'Job Started', 'method': 'metactical.custom_scripts.rabbitmq.integration.integration.connect'})
    else:
        jobs = frappe.get_all('Scheduled Job Log', filters={'status': 'Job Started'})
        
    for job in jobs:
        frappe.db.set_value('Scheduled Job Log', job.name, 'status', 'Stopped')

# Uncomment this line to call the subscription function on script load
# subscribe_to_rabbitmq()
