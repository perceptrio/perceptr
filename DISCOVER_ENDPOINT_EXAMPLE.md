# Discover Endpoint Usage Example

The discover endpoint allows you to process queries using the discover graph, which analyzes user session data to provide insights.

## Endpoint
`POST /api/v1/chat/discover`

## Authentication
Requires Bearer token in Authorization header

## Request Body
```json
{
    "query": "Show me users who had trouble with the checkout process",
    "chat_id": 123  // Optional: if provided, adds to existing chat
}
```

## Response
```json
{
    "chat_id": 123,
    "messages": [
        {
            "id": 456,
            "type": "user",
            "data": {
                "query": "Show me users who had trouble with the checkout process"
            },
            "created_at": "2025-01-19T10:30:00.000Z"
        },
        {
            "id": 457,
            "type": "assistant",
            "data": {
                "content": "Based on the session data analysis, I found 12 users who experienced issues with the checkout process...",
                "full_response": {
                    // Complete discover graph response
                }
            },
            "created_at": "2025-01-19T10:30:05.000Z"
        }
    ]
}
```

## Example Usage

### Create a new chat and discover
```bash
curl -X POST "http://localhost:8000/api/v1/chat/discover" \
     -H "Authorization: Bearer your_access_token" \
     -H "Content-Type: application/json" \
     -d '{
         "query": "Find users who abandoned their shopping carts"
     }'
```

### Add to existing chat
```bash
curl -X POST "http://localhost:8000/api/v1/chat/discover" \
     -H "Authorization: Bearer your_access_token" \
     -H "Content-Type: application/json" \
     -d '{
         "query": "What was the main reason for cart abandonment?",
         "chat_id": 123
     }'
```

## Features
- Creates a new chat automatically if no chat_id is provided
- Uses the query as the chat title (truncated to 100 characters)
- Saves both user query and AI response as chat messages
- Leverages the discover graph for session data analysis
- Proper error handling and authentication

## Additional Chat Endpoints

### Get all chats
`GET /api/v1/chat/`

### Get specific chat
`GET /api/v1/chat/{chat_id}`

### Create a new empty chat
`POST /api/v1/chat/`
```json
{
    "title": "My Analysis Session"
}
``` 