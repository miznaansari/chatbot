import os
import requests
import json
from pymongo import MongoClient
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from bson import ObjectId

load_dotenv()

app = Flask(__name__)
CORS(app)

def connect_to_mongo():
    print("Connecting to MongoDB...")
    try:
        client = MongoClient(os.getenv('MONGO_URI'))
        db = client.Tinder
        print("Successfully connected to MongoDB")
        return db
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None

def query_gemini_api(prompt, user_data=None):
    print("Querying Gemini API...")
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent"
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("API key not found. Please check your environment variables.")
        return "API key not found. Please check your environment variables."

    params = {"key": api_key}

    if user_data:
        user_info = f"User Info: Name: {user_data.get('name', 'Mohd Mizna Ansari')}, Email: {user_data.get('email', 'miznaansari@gmail.com')}, Profile Picture: {user_data.get('profilePicture', 'Not Available')}, DOB: {user_data.get('dob', 'Unknown')}"

        prompt_with_context = f"{user_info}\nUser Question: {prompt}"
    else:
        prompt_with_context = prompt

    data = {"contents": [{"parts": [{"text": prompt_with_context}]}]}

    try:
        response = requests.post(api_url, headers=headers, params=params, json=data)
        print("Received response from Gemini API")
        if response.status_code == 200 and 'candidates' in response.json():
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        print(f"Exception during API call: {e}")
        return f"Error: {e}"

def get_user_data(db, email):
    try:
        user = db.users.find_one({"email": email})
        return user if user else None
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return None

def save_feedback(db, user_input, incorrect_response, correct_response):
    try:
        db.feedback.insert_one({
            'user_input': user_input,
            'incorrect_response': incorrect_response,
            'correct_response': correct_response
        })
        print("Feedback saved. Thank you!")
    except Exception as e:
        print(f"Error saving feedback: {e}")

@app.route('/generate-summary', methods=['POST'])
def generate_summary():
    print("Received /generate-summary request")
    db = connect_to_mongo()
    if db is None:
        return jsonify({"error": "Failed to connect to database"}), 500

    data = request.get_json()
    print("Request data:", data)

    sender_id = data.get('senderId')
    receiver_id = data.get('receiverId')
    custom_prompt = data.get('customPrompt', "Summarize the following conversation")

    if not sender_id or not receiver_id:
        print("Missing sender or receiver ID")
        return jsonify({"error": "Missing sender or receiver ID"}), 400

    try:
        sender_id = ObjectId(sender_id)
        receiver_id = ObjectId(receiver_id)
        print("Converted senderId and receiverId to ObjectId")

        print("Fetching chats from database...")
        chats = list(db.chats.find({
            '$or': [
                {'senderId': sender_id, 'receiverId': receiver_id},
                {'senderId': receiver_id, 'receiverId': sender_id}
            ]
        }))
        print(f"Fetched {len(chats)} chats")

        if not chats:
            print("No chats found between these users")
            return jsonify({"error": "No chats found between these users"}), 404

        chat_text = '\n'.join([f"{chat['senderId']}: {chat['message']}" for chat in chats])
        summary_prompt = f"{custom_prompt}:\n{chat_text}"
        print("Sending chat text to Gemini API for summarization")
        summary = query_gemini_api(summary_prompt)

        print("Summary generated successfully")
        return jsonify({"summary": summary})

    except Exception as e:
        print(f"Error generating chat summary: {e}")
        return jsonify({"error": "Failed to generate chat summary"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    db = connect_to_mongo()
    if db is None:
        return jsonify({"error": "Failed to connect to database"}), 500

    data = request.get_json()
    email = data.get('email')
    user_input = data.get('message')

    if not email or not user_input:
        return jsonify({"error": "Missing email or message"}), 400

    user_data = get_user_data(db, email)

    if not user_data:
        return jsonify({"error": "User not found"}), 404

    response = query_gemini_api(user_input, user_data)
    return jsonify({"response": response})

@app.route('/feedback', methods=['POST'])
def feedback():
    db = connect_to_mongo()
    if db is None:
        return jsonify({"error": "Failed to connect to database"}), 500

    data = request.get_json()
    user_input = data.get('message')
    incorrect_response = data.get('incorrect_response')
    correct_response = data.get('correct_response')

    if not user_input or not incorrect_response or not correct_response:
        return jsonify({"error": "Missing input, incorrect response, or correct response"}), 400

    save_feedback(db, user_input, incorrect_response, correct_response)
    return jsonify({"message": "Feedback submitted successfully"})

if __name__ == "__main__":
    print("Starting Flask server...")
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
