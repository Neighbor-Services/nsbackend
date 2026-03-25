import os
import json
import requests
import logging

logger = logging.getLogger(__name__)

def analyze_content_with_ai(content, resource_type="message"):
    """
    Analyzes content using OpenAI for moderation.
    Returns: { 'safe': bool, 'reason': str, 'sanitized_content': str }
    """
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        logger.warning("OPENAI_API_KEY not found in environment.")
        return {'safe': True, 'reason': 'No API Key', 'sanitized_content': content}

    prompt = f"""
    You are an automated moderation assistant for a service marketplace. 
    Analyze the following {resource_type} for:
    1. PII (phone numbers, emails, physical addresses).
    2. Off-platform payment requests (asking to pay via cash, Venmo, PayPal, etc. outside the site).
    3. Harassment, hate speech, or inappropriate professional conduct.

    Content: "{content}"

    Respond only with a JSON object:
    {{
        "safe": boolean,
        "reason": "short explanation if not safe",
        "should_mask": boolean,
        "masked_content": "content with PII/payment info replaced with [REDACTED] if applicable"
    }}
    """

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()['choices'][0]['message']['content']
            # Clean up potential markdown formatting if model adds it
            result = result.replace('```json', '').replace('```', '').strip()
            return json.loads(result)
        else:
            logger.error(f"OpenAI API Error: {response.text}")
            return {'safe': True, 'reason': 'API Error', 'sanitized_content': content}
            
    except Exception as e:
        logger.error(f"Error in analyze_content_with_ai: {str(e)}")
        return {'safe': True, 'reason': 'Exception', 'sanitized_content': content}
