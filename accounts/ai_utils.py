import os
import base64
import json
import requests
import logging

logger = logging.getLogger(__name__)

def analyze_portfolio_image(image_path):
    """
    Analyzes a portfolio image using OpenAI Vision API.
    Returns: { 'tags': list, 'description': str }
    """
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        logger.warning("OPENAI_API_KEY not found in environment.")
        return {'tags': [], 'description': ''}

    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        prompt = """
        Analyze this image for a professional service portfolio.
        Generate 3-5 relevant tags (keywords) and a professional one-sentence description.
        Respond only with a JSON object:
        {
            "tags": ["tag1", "tag2", "tag3"],
            "description": "Professional description here."
        }
        """

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 300
            },
            timeout=30
        )

        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # Clean possible markdown
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
        else:
            logger.error(f"OpenAI Vision API Error: {response.text}")
            return {'tags': [], 'description': ''}

    except Exception as e:
        logger.error(f"Error in analyze_portfolio_image: {str(e)}")
        return {'tags': [], 'description': ''}
