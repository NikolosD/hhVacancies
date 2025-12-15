"""
AI-powered vacancy filtering using Google Gemini.
Scores vacancies based on relevance to user preferences.
"""

import logging
import google.generativeai as genai
import config

logger = logging.getLogger(__name__)

# Configure Gemini
_model = None


def _get_model():
    """Get or create Gemini model instance."""
    global _model
    if _model is None and config.GEMINI_API_KEY:
        genai.configure(api_key=config.GEMINI_API_KEY)
        
        # Log available models to help debug
        try:
            logger.info("Listing available Gemini models...")
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    logger.info(f"Available model: {m.name}")
        except Exception as e:
            logger.error(f"Failed to list models: {e}")

        # Use available flash model
        _model = genai.GenerativeModel('models/gemini-flash-latest')
    return _model


async def score_vacancy(vacancy: dict, user_prefs: dict = None) -> tuple[int, dict]:
    """
    Score a vacancy using Gemini AI.
    
    Args:
        vacancy: HH.ru vacancy dict
async def score_vacancy(vacancy_data: dict, user_prefs: dict = None) -> tuple[int, dict]:
    """Score vacancy using configured AI provider."""
    
    # 1. Prepare Prompt (Common for all)
    title = vacancy_data.get("name", "Не указано")
    salary = vacancy_data.get("salary")
    salary_str = "Не указана"
    if salary:
        salary_from = salary.get("from")
        salary_to = salary.get("to")
        currency = salary.get("currency", "")
        if salary_from and salary_to:
            salary_str = f"{salary_from} - {salary_to} {currency}"
        elif salary_from:
            salary_str = f"от {salary_from} {currency}"
        elif salary_to:
            salary_str = f"до {salary_to} {currency}"
            
    employer = vacancy_data.get("employer", {}).get("name", "Не указан")
    snippet = vacancy_data.get("snippet", {})
    requirements = snippet.get("requirement") or "Не указаны"
    responsibility = snippet.get("responsibility") or "Не указаны"
    area = vacancy_data.get("area", {}).get("name", "Не указан")
    experience = vacancy_data.get("experience", {}).get("name", "Не указан")
    
    search_query = user_prefs.get("search_query", config.SEARCH_QUERY) if user_prefs else config.SEARCH_QUERY
    
    prompt = f"""Ты HR-эксперт. Оцени релевантность вакансии для соискателя.

ПОИСКОВЫЙ ЗАПРОС СОИСКАТЕЛЯ: {search_query}

ВАКАНСИЯ:
- Название: {title}
- Компания: {employer}
- Зарплата: {salary_str}
- Локация: {area}
- Опыт: {experience}
- Требования: {requirements[:800]}
- Обязанности: {responsibility[:800]}

ЗАДАЧА:
1. Оцени релевантность (0-100).
2. Выдели стек технологий (кратко, через запятую).
3. Напиши 2-3 главных плюса (кратко).
4. Напиши 1-2 минуса или риски (кратко). Отсутствие зарплаты МИНУСОМ НЕ СЧИТАТЬ.
5. Напиши краткий вердикт (одним предложением).

ФОРМАТ ОТВЕТА (JSON):
{{
  "score": 85,
  "stack": "React, TypeScript, Redux, Docker",
  "pros": "Удаленка, ДМС, Крупная компания",
  "cons": "Легаси код, Овертаймы",
  "verdict": "Отличный вариант для роста, но возможны переработки."
}}
Ответь ТОЛЬКО валидным JSON."""

    # 2. Select Provider
    if not config.AI_FILTER_ENABLED:
        logger.warning(f"AI filtering is disabled.")
        return -1, {}

    if config.AI_PROVIDER == "gemini":
        if not config.GEMINI_API_KEY:
            logger.error("Gemini API key not configured.")
            return -1, {}
        return await _score_gemini(prompt, title)
    elif config.AI_PROVIDER in ["openai", "groq"]:
        if not config.OPENAI_API_KEY:
            logger.error(f"{config.AI_PROVIDER} API key not configured.")
            return -1, {}
        return await _score_openai(prompt, title)
    else:
        logger.error(f"Unknown AI provider: {config.AI_PROVIDER}")
        return -1, {}

async def _score_openai(prompt: str, title: str) -> tuple[int, dict]:
    """Score using OpenAI/Groq API."""
    if not openai_client:
        logger.error("OpenAI client not initialized")
        return -1, {}
        
    try:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful HR assistant. Respond ONLY in JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}, # Force JSON mode
            temperature=0.3
        )
        
        text = response.choices[0].message.content
        import json
        data = json.loads(text)
        return _parse_ai_response(data, title)
        
    except Exception as e:
        logger.error(f"OpenAI/Groq scoring failed: {e}")
        return -1, {}

async def _score_gemini(prompt: str, title: str) -> tuple[int, dict]:
    """Score using Google Gemini API."""
    import asyncio
    import re
    
    model = _get_model() # Ensure model is initialized
    if not model:
        logger.error("Gemini model not initialized")
        return -1, {}

    retries = 3
    base_delay = 5
    
    for attempt in range(retries):
        try:
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            
            # Clean up code blocks if present
            if text.startswith("```"):
                text = text.strip("`").replace("json", "").strip()
                
            import json
            data = json.loads(text)
            return _parse_ai_response(data, title)
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "Quota exceeded" in error_str:
                logger.warning(f"AI Rate Limit hit (attempt {attempt+1}/{retries}). Waiting...")
                retry_match = re.search(r"retry in (\d+(\.\d+)?)s", error_str)
                if retry_match:
                    wait_time = float(retry_match.group(1)) + 1
                else:
                    wait_time = base_delay * (2 ** attempt)
                logger.info(f"Sleeping for {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                continue
            
            logger.error(f"AI scoring failed: {e}")
            return -1, {}

    logger.error("AI scoring failed after max retries")
    return -1, {}

def _parse_ai_response(data: dict, title: str) -> tuple[int, dict]:
    """Helper to parse common JSON format."""
    score = int(data.get("score", 0))
    reasoning = {
        "stack": data.get("stack", ""),
        "pros": data.get("pros", ""),
        "cons": data.get("cons", ""),
        "verdict": data.get("verdict", "")
    }
    score = max(0, min(100, score))
    logger.info(f"AI scored '{title}' at {score}/100")
    return score, reasoning


def should_send_vacancy(score: int) -> bool:
    """Check if vacancy should be sent based on AI score."""
    if score < 0:
        return True
    return score >= config.MIN_AI_SCORE
