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
        user_prefs: Optional user preferences dict
        
    Returns:
        Score from 0 to 100, or -1 if AI is disabled/error
    """
    if not config.AI_FILTER_ENABLED or not config.GEMINI_API_KEY:
        logger.warning(f"AI disabled. ENABLED={config.AI_FILTER_ENABLED}, KEY={bool(config.GEMINI_API_KEY)}")
        return -1  # AI disabled
    
    model = _get_model()
    if not model:
        logger.error("Failed to get Gemini model")
        return -1
    
    # Extract vacancy info
    title = vacancy.get("name", "")
    employer = vacancy.get("employer", {}).get("name", "")
    
    salary = vacancy.get("salary")
    salary_str = "Не указана"
    if salary:
        _from = salary.get("from")
        _to = salary.get("to")
        currency = salary.get("currency", "")
        if _from and _to:
            salary_str = f"{_from}-{_to} {currency}"
        elif _from:
            salary_str = f"от {_from} {currency}"
        elif _to:
            salary_str = f"до {_to} {currency}"
    
    experience = vacancy.get("experience", {}).get("name", "")
    area = vacancy.get("area", {}).get("name", "")
    
    # Get snippet if available
    snippet = vacancy.get("snippet", {})
    requirements = snippet.get("requirement", "") or ""
    responsibility = snippet.get("responsibility", "") or ""
    
    # Build search context
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

    try:
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        
        # Clean up code blocks if present
        if text.startswith("```"):
            text = text.strip("`").replace("json", "").strip()
            
        import json
        data = json.loads(text)
        
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
        
    except Exception as e:
        logger.error(f"AI scoring failed: {e}")
        return -1, {}  # Return error values


def should_send_vacancy(score: int) -> bool:
    """Check if vacancy should be sent based on AI score."""
    if score < 0:
        return True  # AI disabled or error, send anyway
    return score >= config.MIN_AI_SCORE
