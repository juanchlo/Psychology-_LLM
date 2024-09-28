from flask import Flask, request, jsonify
import os
import smtplib
import json
import tiktoken
from openai import AzureOpenAI
from dotenv import load_dotenv, dotenv_values
from azure.search.documents.models import VectorizedQuery
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


app = Flask(__name__)
users = []

if os.path.exists(".env"):
    load_dotenv(override=True)
    config = dotenv_values(".env")
    print(config)

azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
azure_openai_chat_completions_deployment_name = os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_DEPLOYMENT_NAME")

azure_openai_embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL")
embedding_vector_dimensions = os.getenv("EMBEDDING_VECTOR_DIMENSIONS")

azure_search_service_endpoint = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
azure_search_service_admin_key = os.getenv("AZURE_SEARCH_SERVICE_ADMIN_KEY")
search_index_name = os.getenv("SEARCH_INDEX_NAME")

email_sender = os.getenv("EMAIL_SENDER")
email_password = os.getenv("EMAIL_PASSWORD")
smtp_server = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT", 587))  # 587 es el valor predeterminado



openai_client = AzureOpenAI(
    azure_endpoint=azure_openai_endpoint,
    api_key=azure_openai_api_key,
    api_version="2024-06-01"
)

search_client = SearchClient(endpoint=azure_search_service_endpoint, index_name=search_index_name, credential=AzureKeyCredential(azure_search_service_admin_key))

# Functions
## Get tokens in query
def num_tokens_from_string(string: str) -> int:
    encoding = tiktoken.get_encoding(encoding_name="cl100k_base")
    num_tokens = len(encoding.encode(string, disallowed_special=()))
    return num_tokens

# Generate embeddings for query
def get_embeddings_vector(text):
    response = openai_client.embeddings.create(
        input=text,
        model=azure_openai_embedding_model,
    )
    return response.data[0].embedding

# Vector similarity check
def query_azure_search(query):
    embedding = get_embeddings_vector(query)
    vector_query = VectorizedQuery(
        vector=embedding, 
        k_nearest_neighbors=3, 
        fields="vector"
    )
    
    results = search_client.search(  
        search_text=None,
        vector_queries=[vector_query],
        select=["page_title", "page_date", "chunk_title", "chunk_content"],
        top=10  # Ajusta este número según tus necesidades
    )  
    
    formatted_results = []
    for result in results:
        page_title = result.get("page_title", "Sin título")
        page_date = result.get("page_date", "Fecha desconocida")
        chunk_title = result.get("chunk_title", "Sin subtítulo")
        chunk_content = result.get("chunk_content", "Sin contenido")
        
        formatted_results.append({
            "title": page_title,
            "date": page_date,
            "section": chunk_title,
            "content": chunk_content
        })
    
    return formatted_results

# Función para enviar correo electrónico
def send_email(to_email, subject, body):
    print("exec")

    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_sender, email_password)
            server.send_message(msg)
        print("Test email sent successfully!")
    except Exception as e:
        print(f"Error sending test email: {str(e)}")
        
# Definición de las funciones disponibles para el modelo
functions = [
    {
        "name": "send_email",
        "description": "Envía un correo electrónico al paciente",
        "parameters": {
            "type": "object",
            "properties": {
                "to_email": {
                    "type": "string",
                    "description": "La dirección de correo electrónico del destinatario"
                },
                "subject": {
                    "type": "string",
                    "description": "El asunto del correo electrónico"
                },
                "body": {
                    "type": "string",
                    "description": "El cuerpo del correo electrónico"
                }
            },
            "required": ["to_email", "subject", "body"]
        }
    }
]

# User query


@app.route('/search', methods=['POST'])
def get_answer():
    # Parse the JSON request body
    message = request.get_json()
    print(message)
    
    if not message or 'query' not in message:
        return jsonify({"error": "Invalid input"}), 400
    
    query = message['query']

    search_results = query_azure_search(query) 
    response = openai_client.chat.completions.create(
        model=azure_openai_chat_completions_deployment_name,
        messages=[
            {"role": "system", "content": "You are an excellent professional psychologist, you help patients and researchers thanks to the information you have available thanks to the search results. You will respond in the language spoken to you with kindness and empathy."},
            {"role": "user", "content": query},
            {"role": "system", "content": f"Search results: {search_results[0]}"},
            {"role": "system", "content": "If the user wants an email, do not ask for confirmation, just send it"},
    ],
    functions=functions,
    function_call="auto"
    )

    print(type(response))
    
    # Procesar la llamada a la función desde la respuesta
    # Extraer la función y los argumentos desde el objeto de respuesta (si es de tipo objeto, como ChatCompletion)
    if response.choices[0].finish_reason == "function_call":
        function_call = response.choices[0].message.function_call
        function_name = function_call.name
        arguments = json.loads(function_call.arguments)  # Convertir los argumentos a un dict

        # Verificar si la función es 'send_email' y ejecutar la lógica
        if function_name == "send_email":
            to_email = arguments['to_email']
            subject = arguments['subject']
            body = arguments['body']
            
            print(to_email, subject, body)
            # Llamar a la función para enviar el correo electrónico
            send_email(to_email, subject, body)
      
    # Return the response as JSON
    openai_response_content = response.choices[0].message.content

    # Prepare a detailed response
    combined_response = {
        "openai_response": openai_response_content,
        "search_results": search_results
    }

    # Return the combined response as JSON
    print(combined_response)
    return jsonify(combined_response)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    username = data.get('username')
    birthdate = data.get('birthdate')

    if any(user['email'] == email for user in users):
        return jsonify({'message': 'User already exist'}), 409
    users.append({
        'email': email,
        'password': password,  # In production, hash passwords!
        'username': username,
        'birthdate': birthdate
    })
    return jsonify({"message": "Signup successful!"}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    # Check user credentials
    user = next((user for user in users if user['email'] == email and user['password'] == password), None)
    if user:
        return jsonify({"message": "Login successful!", "user": user}), 200
    return jsonify({"message": "Invalid credentials!"}), 401

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

    
    