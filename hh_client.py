import httpx
import logging
import config

logger = logging.getLogger(__name__)

async def get_vacancies(
    text: str = None,
    min_salary: int = None,
    experience: str = None,
    area: str = None,
    schedule: str = None
):
    """
    Fetches vacancies from HH.ru API with optional filters.
    Docs: https://github.com/hhru/api/blob/master/docs/vacancies.md
    
    Experience values: noExperience, between1And3, between3And6, moreThan6
    Schedule values: remote, fullDay, shift, flexible
    """
    url = "https://api.hh.ru/vacancies"
    
    # Use config defaults if not specified
    text = text or config.SEARCH_QUERY
    min_salary = min_salary if min_salary is not None else config.MIN_SALARY
    experience = experience or config.EXPERIENCE
    area = area if area is not None else config.AREA
    schedule = schedule or getattr(config, 'SCHEDULE', '')
    
    params = {
        "text": text,
        "order_by": "publication_time",
        "per_page": 20,
        "search_field": "name",
    }
    
    # Add area filter
    if area:
        params["area"] = area
    
    # Add salary filter
    if min_salary > 0:
        params["salary"] = min_salary
        params["only_with_salary"] = "true"
    
    # Add experience filter
    if experience:
        params["experience"] = experience
    
    # Add schedule filter (e.g., remote)
    if schedule:
        params["schedule"] = schedule
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            vacancies = data.get("items", [])
            
            # Additional client-side salary filtering (HH API isn't always precise)
            if min_salary > 0:
                vacancies = [v for v in vacancies if _salary_meets_minimum(v, min_salary)]
            
            return vacancies
        except Exception as e:
            logger.error(f"Error fetching vacancies: {e}")
            return []


def _salary_meets_minimum(vacancy: dict, min_salary: int) -> bool:
    """Check if vacancy salary meets minimum requirement."""
    salary = vacancy.get("salary")
    if not salary:
        return False
    
    sal_from = salary.get("from") or 0
    sal_to = salary.get("to") or 0
    
    # If salary is in USD or EUR, multiply by approximate rate
    currency = salary.get("currency", "RUR")
    multiplier = 1
    if currency == "USD":
        multiplier = 90
    elif currency == "EUR":
        multiplier = 100
    
    max_salary = max(sal_from, sal_to) * multiplier
    return max_salary >= min_salary


def format_vacancy(vacancy: dict) -> str:
    """Format a vacancy dict into a nice string for Telegram."""
    title = vacancy.get("name", "No Title")
    url = vacancy.get("alternate_url", "")
    salary = vacancy.get("salary")
    
    salary_str = "💰 Зарплата не указана"
    if salary:
        _from = salary.get("from")
        _to = salary.get("to")
        currency = salary.get("currency", "")
        
        if _from and _to:
            salary_str = f"💰 {_from:,} - {_to:,} {currency}".replace(",", " ")
        elif _from:
            salary_str = f"💰 от {_from:,} {currency}".replace(",", " ")
        elif _to:
            salary_str = f"💰 до {_to:,} {currency}".replace(",", " ")

    employer = vacancy.get("employer", {}).get("name", "Unknown Company")
    area = vacancy.get("area", {}).get("name", "")
    
    # Experience
    exp = vacancy.get("experience", {}).get("name", "")
    exp_str = f"📊 {exp}" if exp else ""

    lines = [
        f"🔥 <b>{title}</b>",
        f"🏢 {employer} ({area})",
        salary_str,
    ]
    if exp_str:
        lines.append(exp_str)
    lines.append(f"\n🔗 {url}")
    
    return "\n".join(lines)
