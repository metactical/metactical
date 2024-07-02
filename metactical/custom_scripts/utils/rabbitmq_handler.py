import frappe
import pika
import json

def publish_to_rabbitmq(server_ip, exchange, exchange_type, routing_key, message, username, password, queue_name):
    try:
        credentials = pika.PlainCredentials(username, password)
        parameters = pika.ConnectionParameters(host=server_ip, credentials=credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Declare a persistent topic exchange
        channel.exchange_declare(exchange=exchange, exchange_type=exchange_type, durable=True)
        frappe.logger().info(f"Exchange declared: {exchange} (type: {exchange_type})")
        
        # Declare a durable queue
        channel.queue_declare(queue=queue_name, durable=True)
        frappe.logger().info(f"Queue declared: {queue_name}")
        
        # Bind the queue to the exchange with the given routing key
        channel.queue_bind(exchange=exchange, queue=queue_name, routing_key=routing_key)
        frappe.logger().info(f"Queue bound to exchange: {queue_name} -> {exchange} (routing key: {routing_key})")
        
        # Publish the message
        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            ))
        frappe.logger().info(f"Message published to exchange: {exchange} (routing key: {routing_key})")
        
        connection.close()
    except Exception as e:
        frappe.logger().error(f"Error publishing message: {str(e)}")
        raise e

@frappe.whitelist(allow_guest=True)
def webhook():
    data = frappe.request.get_json()

    # Check for missing required fields
    required_fields = ['server_ip', 'exchange', 'exchange_type', 'routing_key', 'queue_name', 'username', 'password', 'message']
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        error_message = f"Missing required fields: {', '.join(missing_fields)}"
        frappe.logger().error(error_message)
        frappe.throw(error_message)

    # Extract RabbitMQ configuration from the incoming request
    server_ip = data['server_ip']
    exchange = data['exchange']
    exchange_type = data['exchange_type']
    routing_key = data['routing_key']
    queue_name = data['queue_name']
    username = data['username']
    password = data['password']
    message = data['message']

    # Log received data for debugging
    frappe.logger().info(f"Received data: {data}")

    # Publish to RabbitMQ
    publish_to_rabbitmq(server_ip, exchange, exchange_type, routing_key, message, username, password, queue_name)

    return {'status': 'Message published to RabbitMQ'}
