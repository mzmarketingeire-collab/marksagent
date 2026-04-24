"""
LLM Router
Routes requests to appropriate model (Google first, then backup)
"""

import os
import google.generativeai as genai
import openai
from decimal import Decimal

class LLMRouter:
    def __init__(self, budget_monitor, audit_logger):
        self.budget = budget_monitor
        self.audit = audit_logger
        
        # Setup Google AI
        google_key = os.getenv('GOOGLE_API_KEY')
        if google_key:
            genai.configure(api_key=google_key)
        
        # Setup OpenRouter
        self.openrouter_key = os.getenv('OPENROUTER_API_KEY')
        openai.api_key = self.openrouter_key
        openai.api_base = "https://openrouter.io/api/v1"
    
    async def route_request(self, task_type, prompt, max_tokens=1000):
        """Route request to best model"""
        
        # Try Google first (FREE - 1500 calls/day!)
        response = await self._call_google(prompt, max_tokens)
        
        if response['success']:
            return response
        
        # Fallback to OpenRouter
        response = await self._call_openrouter(prompt, max_tokens)
        
        return response
    
    async def _call_google(self, prompt, max_tokens):
        """Call Google Gemini API (FREE!)"""
        try:
            model = genai.GenerativeModel('gemini-pro')
            
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7
                )
            )
            
            content = response.text
            tokens = len(content.split())
            
            await self.audit.log('google_api_success', {
                'tokens': tokens,
                'cost': 0
            })
            
            return {
                'success': True,
                'content': content,
                'tokens': tokens,
                'cost': Decimal('0.0'),
                'model': 'google-gemini'
            }
        
        except Exception as e:
            print(f"Google API error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _call_openrouter(self, prompt, max_tokens):
        """Call OpenRouter as fallback"""
        try:
            # Check budget
            estimated_cost = Decimal('0.001')
            budget_ok, msg = await self.budget.check_budget(estimated_cost)
            
            if not budget_ok:
                await self.audit.log('api_call_blocked', {'reason': 'budget'}, 'warning')
                return {
                    'success': False,
                    'error': 'Budget limit reached'
                }
            
            response = openai.ChatCompletion.create(
                model="minimax/minimax-text-latest",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens
            )
            
            content = response['choices'][0]['message']['content']
            tokens = response['usage']['total_tokens']
            cost = Decimal('0.0001') * tokens
            
            await self.budget.log_api_call('minimax', tokens, cost, 'openrouter', True)
            await self.audit.log('openrouter_success', {
                'tokens': tokens,
                'cost': float(cost)
            })
            
            return {
                'success': True,
                'content': content,
                'tokens': tokens,
                'cost': cost,
                'model': 'minimax'
            }
        
        except Exception as e:
            print(f"OpenRouter error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

import time

print("Bot starting...")

while True:
    time.sleep(60)
