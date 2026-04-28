# Post-Deployment Notes – Branch Home Today Counts & Live Updates

## 1. Current Setup

### Branch Home Today Cards

Branch Home lo today cards customer-based ga set chesam:

- Total Customers
- Offer Claimed
- New Customers
- Repeated Customers

Current mapping:

```text
Total Customers    → total_today_customers
Offer Claimed      → today_offer_claims / offer_claims
New Customers      → new_customers
Repeated Customers → repeated_customers
```

### Customer Count Logic

Today customer logic separate service helper lo move chesam:

```python
get_branch_today_customer_summary_counts()
```

Logic:

```text
Total Today Customers:
  Today current branch lo visit chesina unique users

New Customers:
  Today visit chesaru
  + same branch lo today mundu previous visit ledu

Repeated Customers:
  Today visit chesaru
  + same branch lo today mundu previous visit undhi
```

### All-Time Customer Logic

All Visits page all-time customer summary logic service helper lo move chesam:

```python
get_branch_all_time_customer_summary_counts()
```

Logic:

```text
One-time Customers:
  Branch lo exactly 1 visit unna users

Repeated Customers:
  Branch lo 2 or more visits unna users

Returning Rate:
  repeated_customers / total_customers * 100
```

---

## 2. Service File Structure

Service file:

```text
offers/services/branch_api/branch_today_metrics_service.py
```

Contains:

```python
get_branch_all_time_customer_summary_counts()
get_branch_today_customer_summary_counts()
get_branch_today_visits_live_data()
```

Purpose:

```text
Views lo heavy count/query logic avoid cheyyadam
Business formulas one place lo maintain cheyyadam
Future lo branch home / live cards reuse easy cheyyadam
```

Required folder files:

```text
offers/services/__init__.py
offers/services/branch_api/__init__.py
offers/services/common/__init__.py
```

---

## 3. Live Update Endpoint

Live endpoint function name:

```python
branch_today_visits_live
```

URL name:

```python
branch_today_visits_live
```

Suggested URL path:

```python
path(
    "branch/today-visits/live/",
    bviews.branch_today_visits_live,
    name="branch_today_visits_live",
)
```

This endpoint should return JSON like:

```json
{
  "ok": true,
  "today": {
    "total_today_customers": 0,
    "new_customers": 0,
    "repeated_customers": 0,
    "offer_claims": 0,
    "returning_rate": 0,
    "new_customer_rate": 0
  }
}
```

---

## 4. Template Live JS

Template file:

```text
today_visits_card.html
```

Live JS should fetch:

```django
{% url 'offers:branch_today_visits_live' %}
```

Card IDs:

```html
todayCustomersCount
todayOfferClaimsCount
todayNewCustomersCount
todayRepeatedCustomersCount
```

Update mapping:

```javascript
total_today_customers → todayCustomersCount
offer_claims          → todayOfferClaimsCount
new_customers         → todayNewCustomersCount
repeated_customers    → todayRepeatedCustomersCount
```

---

## 5. Production Polling Recommendation

Current live refresh interval can be:

```javascript
window.setInterval(refreshTodayVisitCounts, 6000);
```

For production, better:

```javascript
window.setInterval(refreshTodayVisitCounts, 10000);
```

or safer:

```javascript
window.setInterval(refreshTodayVisitCounts, 15000);
```

Reason:

```text
6 seconds is okay for development.
Production lo many branch dashboards open unte DB load increase avvachu.
10–15 seconds is enough for restaurant dashboard live cards.
```

---

## 6. Database Indexes to Add Later

After deployment or before heavy usage, add indexes for performance.

Recommended indexes:

```text
UserVisitEvent(branch, created_at)
UserVisitEvent(branch, user, created_at)
UserOfferClaim(branch, issued_at)
UserOfferClaim(visit_event)
```

Why:

```text
Today counts use branch + created_at range
New/repeated customer logic uses branch + user + created_at
Offer claim count uses branch + issued_at
History claim count uses visit_event
```

---

## 7. Important Performance Notes

### Today Live API

Each refresh does a few count queries:

```text
today visit aggregate
today offer claims count
today total/new/repeated customer counts
```

This is okay for small/medium traffic.

Production risk only if:

```text
many branch dashboard tabs stay open
polling interval too low
large visit table without indexes
```

### All Visits Page

All Visits page has heavier logic:

```text
search
pagination
grouping by users
history load more
claim count mapping
```

Already mitigated by:

```text
CUSTOMERS_PER_PAGE = 50
HISTORY_LIMIT_PER_USER = 30
AJAX table refresh
history load-more endpoint
```

Keep these limits.

---

## 8. Naming Rules Going Forward

Use clear names to avoid confusion.

```text
branch_today_visits_live
→ Branch Home today cards live update

branch_all_visits_table_live
→ All Visits table search/pagination live update

branch_visit_history_live
→ User visit history load-more endpoint
```

Avoid vague names like:

```text
branch_live_api
branch_all_visits_live
```

They can confuse future work.

---

## 9. After Deployment Checklist

- Confirm `branch_today_visits_live` route exists in `urls.py`
- Confirm `today_visits_card.html` fetches correct URL
- Confirm card IDs match JS node IDs
- Confirm service file import works without `ModuleNotFoundError`
- Confirm `__init__.py` files exist in service folders
- Confirm Branch Home updates without page refresh
- Confirm All Visits search/pagination still works
- Confirm history load-more still works
- Increase polling interval to 10–15 seconds
- Add DB indexes before large production data
- Clean duplicate imports in `branch_views.py`
- Later move remaining large context logic into service files if needed

---

## 10. Future Cleanup

Later, create separate service for All Visits context:

```text
offers/services/branch_api/branch_all_visits_context_service.py
```

Move this only after current features are stable:

```python
build_branch_visits_context()
```

Do not move too much at once. First deploy stable, then refactor.

---

## 11. Quick Verification Commands

Search old vague names:

```powershell
Get-ChildItem -Recurse -File -Include *.py,*.html,*.js |
Select-String -Pattern "branch_live_api|branch_all_visits_live" |
Select-Object Path, LineNumber, Line
```

Search new names:

```powershell
Get-ChildItem -Recurse -File -Include *.py,*.html,*.js |
Select-String -Pattern "branch_today_visits_live|branch_all_visits_table_live" |
Select-Object Path, LineNumber, Line
```

Expected files for `branch_today_visits_live`:

```text
offers/branch_views.py
offers/urls.py
offers/templates/branch/partials/today_visits_card.html
```

Expected files for `branch_all_visits_table_live`:

```text
offers/branch_views.py
offers/urls.py
offers/templates/branch/branch_all_visits/partials/allvisits_record_table/allvisits_record_table.html
```

---

## 12. Current Clean Separation

```text
branch_views.py
→ request/session/render/json response

branch_today_metrics_service.py
→ DB count formulas and today live card data

time_helpers.py
→ day_start / next_day_start common helper

today_visits_card.html
→ display + live JS

urls.py
→ route names
```

This separation keeps views clean and avoids future confusion between all-time metrics and today metrics.
