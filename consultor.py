import os
import requests
import psycopg2  # Conexión con PostgreSQL
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)
CORS(app)

class SQLChatBot:
    def __init__(self):
        """Inicializa la configuración de la base de datos y la API de OpenAI."""
        self.db_url = os.getenv("DATABASE_URL")  # Render proporciona la URL completa de PostgreSQL
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

    def connect_db(self):
        """Conecta a PostgreSQL usando psycopg2."""
        try:
            conn = psycopg2.connect(self.db_url, sslmode="require")  # SSL obligatorio en Render
            return conn
        except psycopg2.Error as e:
            print(f"❌ Error conectando a PostgreSQL: {e}")
            return None

    def execute_query(self, sql_query):
        """Ejecuta la consulta SQL en PostgreSQL y devuelve los resultados."""
        conn = self.connect_db()
        if not conn:
            return None, "No se pudo conectar a la base de datos."

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql_query)
                result = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
            conn.close()
            return [dict(zip(columns, row)) for row in result], None
        except psycopg2.Error as e:
            return None, f"Error en la base de datos: {str(e)}"

    def get_sql_query_from_openai(self, user_input):
        """Convierte lenguaje natural a SQL para PostgreSQL usando OpenAI."""
        headers = {"Authorization": f"Bearer {self.openai_api_key}"}
        payload = {
            "model": "gpt-4-turbo",
            "messages": [
                {"role": "system", "content": 
                    "Eres un asistente experto en SQL para PostgreSQL. La base de datos contiene la tabla 'public.usuarios' con las siguientes columnas:\n"
                    "- id (SERIAL) -> Identificador único del usuario (PRIMARY KEY)\n"
                    "- nombre (VARCHAR) -> Nombre del usuario\n"
                    "- email (VARCHAR) -> Correo electrónico (único)\n"
                    "- edad (INT) -> Edad del usuario\n"
                    "Responde SOLO con la consulta SQL correcta para PostgreSQL. No expliques nada, solo responde con la consulta SQL sin formateo adicional."
                },
                {"role": "user", "content": f"Convierte esta consulta a SQL: {user_input}"}
            ],
            "max_tokens": 100
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)

        if response.status_code == 200:
            sql_query = response.json()["choices"][0]["message"]["content"]
            sql_query = sql_query.strip().replace('```sql', '').replace('```', '')
            return sql_query
        else:
            print(f"❌ Error en la API de OpenAI: {response.json()}")
            return None

    def get_enhanced_response(self, query_result):
        """Genera una explicación detallada de los resultados usando OpenAI."""
        headers = {"Authorization": f"Bearer {self.openai_api_key}"}
        payload = {
            "model": "gpt-4-turbo",
            "messages": [
                {"role": "system", "content": 
                    "Eres un asistente que ayuda a interpretar respuestas de una base de datos SQL."
                    "Dado un conjunto de resultados de una consulta SQL, genera una respuesta explicativa en lenguaje natural."
                    "No muestres la consulta SQL ni los datos en crudo, solo proporciona una explicación clara."
                },
                {"role": "user", "content": f"Interpreta estos resultados y genera una respuesta detallada para el usuario: {query_result}"}
            ],
            "max_tokens": 200
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"❌ Error en la API de OpenAI: {response.json()}")
            return None

sql_chatbot = SQLChatBot()

@app.route("/query", methods=["POST"])
def query_database():
    """Ejecuta una consulta SQL generada por OpenAI y devuelve los resultados."""
    data = request.json
    user_input = data.get("userInput")

    if not user_input:
        return jsonify({"error": "Falta el parámetro 'userInput'"}), 400

    try:
        sql_query = sql_chatbot.get_sql_query_from_openai(user_input)
        print(f"📝 Consulta generada por OpenAI:\n{sql_query}")

        if not sql_query:
            return jsonify({"error": "No se pudo generar la consulta SQL"}), 500

        results, db_error = sql_chatbot.execute_query(sql_query)

        if db_error:
            return jsonify({"error": db_error}), 500

        detailed_response = sql_chatbot.get_enhanced_response(results)

        return jsonify({"data": results, "enhanced_response": detailed_response})

    except Exception as e:
        return jsonify({"error": f"Error general: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(port=3001, debug=True)
