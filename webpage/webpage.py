import streamlit as st
import requests

# Initialize session state for login status and messages
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if 'messages' not in st.session_state:
    st.session_state.messages = []  # Initialize the messages in session state

# Function to sign up a user via the Flask API
def signup_to_flask(email, password, username, birthdate):
    response = requests.post("http://flask:5000/signup", json={
        "email": email,
        "password": password,
        "username": username,
        "birthdate": birthdate
    })
    return response.json()

# Function to log in a user via the Flask API
def login_to_flask(email, password):
    response = requests.post("http://flask:5000/login", json={
        "email": email,
        "password": password
    })
    if response.status_code == 200:  # Check if login is successful
        st.session_state.logged_in = True  # Set login state to True
    return response.json()

def query_rag(query):
    response = requests.post("http://flask:5000/search", json={"query": query})
    print("Response status:", response.status_code)  # Debugging line
    if response.status_code == 200:
        return response.json()  # Return the JSON content
    else:
        return {"error": "Error querying API"}


# Function to display the chat page
def chat_page():
    st.title("Conversa con Leo, tu psicólogo de confianza.")

    # Display chat messages stored in session_state
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.chat_message("user").markdown(message["content"])
        else:
            st.chat_message("assistant").markdown(message["content"])

    # Input box for user to enter a prompt
    if prompt := st.chat_input("What is up?"):
        # Store user message in session_state
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Call the query function
        response = query_rag(prompt)
        print("Response from query_rag:", response)  # Debugging line

        # Check if the response contains the expected keys
        if "openai_response" in response and "search_results" in response:
            openai_response = response["openai_response"]
            search_results = response["search_results"]
            
            # Format the results
            results = f"{openai_response}"
        else:
            results = "No results found or an error occurred."

        # Store assistant response in session_state
        with st.chat_message("assistant"):
            st.markdown(results)
        st.session_state.messages.append({"role": "assistant", "content": results})


# Function to display the login page
def login_page():
    st.title("Login")
    choice = st.selectbox('Signup/Login', ['Signup', 'Login'])

    # Collect inputs based on the choice (Signup/Login)
    email = st.text_input('Email')
    password = st.text_input('Password', type='password')

    if choice == 'Signup':
        username = st.text_input('Username')
        birthdate = st.text_input('Birth date (MM/DD/YYYY)')
    else:
        username = None
        birthdate = None

    # Submit button
    submit = st.button('Submit')

    # Process the form submission
    if submit:
        if email and password:  # Ensure both fields are filled
            if choice == 'Signup' and username and birthdate:  # Additional fields for Signup
                result = signup_to_flask(email, password, username, birthdate)
                st.success(result.get('message', 'Signed up successfully!'))
            elif choice == 'Login':
                result = login_to_flask(email, password)
                st.success(result.get('message', 'Logged in successfully!'))

                # If login is successful, update the query params to force rerun
                if st.session_state.logged_in:
                    st.session_state.previous_page = "chat"
                    logged_in = st.query_params.get("logged_in") == ["true"]
            else:
                st.error('Please fill in all fields for signup.')
        else:
            st.error('Please enter both email and password.')

# Main app logic
if st.session_state.logged_in or st.query_params.get("logged_in") == ["true"]:
    chat_page()  # User is logged in, show chat page
elif "previous_page" in st.session_state and st.session_state.previous_page == "chat":
    chat_page()  # Redirect to chat page if logged in before
else:
    login_page()  # Show login page if not logged in
