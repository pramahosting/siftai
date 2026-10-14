def eligible(event: dict) -> bool:
    if event.get("isCancelled") or event.get("isAllDay"): return False
    if (event.get("sensitivity") or "normal").lower()=="private": return False
    response=(event.get("responseStatus") or {}).get("response", "")
    return response in {"accepted","tentativelyAccepted"}

def count_words(text: str) -> int:
    return len(text.split())
