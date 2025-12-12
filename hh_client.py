import httpx
import logging

logger = logging.getLogger(__name__)

async def get_vacancies(text: str = "Frontend React"):
    """
    Fetches vacancies from HH.ru API.
    Docs: https://github.com/hhru/api/blob/master/docs/vacancies.md
    """
    url = "https://api.hh.ru/vacancies"
    params = {
        "text": text,
        "order_by": "publication_time", # Sort by newest
        "per_page": 20, # Get last 20
        "area": 113, # 113 is Russia. You can remove this or change to specific city if needed. 
                     # Or pass None to search everywhere.
        "search_field": "name", # Search in title
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except Exception as e:
            logger.error(f"Error fetching vacancies: {e}")
            return []

def format_vacancy(vacancy):
    """
    Format a vacancy dict into a nice string for Telegram.
    """
    title = vacancy.get("name", "No Title")
    url = vacancy.get("alternate_url", "")
    salary = vacancy.get("salary")
    
    salary_str = "Зарплата не указана"
    if salary:
        _from = salary.get("from")
        _to = salary.get("to")
        currency = salary.get("currency", "")
        
        if _from and _to:
            salary_str = f"{_from} - {_to} {currency}"
        elif _from:
            salary_str = f"от {_from} {currency}"
        elif _to:
            salary_str = f"до {_to} {currency}"

    employer = vacancy.get("employer", {}).get("name", "Unknown Company")
    area = vacancy.get("area", {}).get("name", "")

    return f"🔥 <b>{title}</b>\n🏢 {employer} ({area})\n💰 {salary_str}\n\n🔗 {url}"
