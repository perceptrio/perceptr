import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_signup_and_login():
    # 1. Create a new organization
    signup_data = {
        "name": "Test User",
        "email": "test@example.com",
        "password": "testpassword123"
    }
    
    response = requests.post(
        f"{BASE_URL}/orgs/signup",
        json=signup_data
    )
    print("\nSignup Response:", json.dumps(response.json(), indent=2))
    
    # 2. Login with the new user
    login_data = {
        "email": "test@example.com",
        "password": "testpassword123"
    }
    
    response = requests.post(
        f"{BASE_URL}/orgs/login",
        json=login_data
    )
    print("\nLogin Response:", json.dumps(response.json(), indent=2))
    token = response.json()["access_token"]
    
    # 3. Get user profile with token
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{BASE_URL}/orgs/me",
        headers=headers
    )
    print("\nProfile Response:", json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    test_signup_and_login() 