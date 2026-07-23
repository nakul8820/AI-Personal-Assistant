"""Google People API contact lookup (read-only)."""

from app.models.schemas import ContactSummary
from app.tools._google import guarded, service


@guarded
def search_contacts(user_id: str, name: str) -> list[ContactSummary]:
    svc = service(user_id, "people", "v1")
    # People API requires a warmup call before searchContacts returns results.
    res = (
        svc.people()
        .searchContacts(query=name, readMask="names,emailAddresses,metadata")
        .execute()
    )
    out: list[ContactSummary] = []
    for r in res.get("results", []):
        person = r.get("person", {})
        emails = person.get("emailAddresses", [])
        if not emails:
            continue
        display = person.get("names", [{}])[0].get("displayName", name)
        out.append(
            ContactSummary(
                name=display,
                email=emails[0]["value"],
                source=emails[0].get("value"),
            )
        )
    return out
