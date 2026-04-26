# Branch Dashboard Right Card – Modification Notes

**Date:** 26-Apr-2026  
**Project:** OfferZone / Django Branch Dashboard  
**Scope:** Branch home page lo right-side card modifications – customer summary + offer claimed percentage.

---

## 1. Main Goal

Right card lo old “last week / increment” type comparison ni remove/comment chesi, branch ki immediate ga useful ayye live business metrics show cheyyadam:

- **New Customers Today**
- **Repeat Customers Today**
- **Offer Claimed %**

Ee logic branch-wise ga undali. Ante oka customer vere branch lo visited aina, current branch lo first time visit chesthe current branch perspective lo **new customer** ga count avvali.

---

## 2. Source of Truth

### Visit source

```python
UserVisitEvent
```

Reason:
- Branch visit record actual ga ikkade store avutundi.
- QR scan / QR + PIN / offer-day PIN type visits anni `UserVisitEvent` lo track avutayi.
- Login mandatory kabatti `UserVisitEvent.user` ni reliable identity ga treat cheyyachu.

### Offer claim source

```python
UserOfferClaim
```

Reason:
- Offer claimed / issued / redeemed data ki source of truth idi.
- User side lo claim issue ayyaka `UserOfferClaim` record create avutundi.

---

## 3. Model Changes

### New model create cheyyaledu

No new model required.

Reason:
- Existing `UserVisitEvent` and `UserOfferClaim` tables lo required data already undi.
- New/repeat customers counts-only requirement kabatti extra table unnecessary.
- Server performance kosam direct DB queries / aggregates use cheyyadam better.

### Migration required?

No migration required.

Reason:
- DB schema change em ledu.
- Only helper + view context + template rendering changes matrame.

---

## 4. Helper File Used / Created

Helper function:

```python
def get_branch_customer_summary_counts(branch):
    ...
```

Recommended/helper path:

```text
offers/helpers/branch_customer_summary.py
```

Mee project lo helper ni vere file lo pettunte, path ni actual file name tho match cheskovali. Important point: helper function name and purpose same.

### Why helper create chesam?

View lo heavy counting logic pedithe `views.py` messy avuthundi. Helper file lo isolate chesthe:

- View clean ga untundi.
- Same counts future lo vere branch pages lo reuse cheyyachu.
- Testing easy.
- Business logic one place lo untundi.

---

## 5. Helper Function Responsibility

`get_branch_customer_summary_counts(branch)` function current branch ki today-based summary calculate chestundi.

Return structure example:

```python
{
    "new_customers_today": new_customers_today,
    "repeat_customers_today": repeat_customers_today,
    "offer_claimed_today": offer_claimed_today,
    "offer_claimed_percent": offer_claimed_percent,
}
```

---

## 6. Date Logic Used

Today calculation ki Django timezone use cheyyali:

```python
from django.utils import timezone

today = timezone.localdate()
```

Reason:
- Server timezone mismatch issue avoid cheyyadaniki.
- India/local business day logic consistent ga undadaniki.

Preferred filtering:

```python
created_at__date=today
```

or performance-heavy traffic unte day start/end range use cheyyachu:

```python
start = timezone.make_aware(datetime.combine(today, time.min))
end = timezone.make_aware(datetime.combine(today, time.max))
```

---

## 7. New Customer Formula

### Definition

Current branch lo user first-ever visit today aithe, that user = **New Customer Today**.

### Formula

```text
New Customers Today = count(users whose first visit in current branch is today)
```

### Conceptual query logic

```python
first_visit_date_for_user_in_branch == today
```

Important:
- User vere branch lo old customer aina parvaledu.
- Current branch lo first time today visit chesthe new customer ga count avvali.

---

## 8. Repeat Customer Formula

### Definition

Current branch lo user today visit chesi, same branch lo today mundu at least one visit unte, that user = **Repeat Customer Today**.

### Formula

```text
Repeat Customers Today = count(users who visited current branch today AND had earlier visit in same branch before today)
```

Alternative safe formula:

```text
Repeat Customers Today = Today Unique Customers - New Customers Today
```

But idi correct ga work avvali ante `Today Unique Customers` only logged-in users distinct count avvali.

---

## 9. Offer Claimed % Formula

### Goal

Last week increment/comparison badulu, right card lo today offer claim conversion percentage show cheyyadam.

### Formula used

```text
Offer Claimed % = (Today Offer Claims / Today Branch Visits) × 100
```

### Python safe formula

```python
offer_claimed_percent = round((offer_claimed_today / today_visits) * 100) if today_visits else 0
```

### Why `if today_visits else 0`?

Today visits zero unte division by zero error vastundi. So safe fallback 0%.

### Example

```text
Today visits = 50
Today offer claims = 10
Offer Claimed % = (10 / 50) × 100 = 20%
```

---

## 10. View File Modified

Main view file:

```text
offers/views.py
```

Modified area:

```python
branch_home / branch_dashboard / branch home related view
```

Exact function name mee project lo current branch home view name batti untundi.

### What changed in view?

Helper import add chesam:

```python
from offers.helpers.branch_customer_summary import get_branch_customer_summary_counts
```

Branch object already available unna place lo helper call chesam:

```python
customer_summary = get_branch_customer_summary_counts(branch)
```

Context lo pass chesam:

```python
context.update({
    "customer_summary": customer_summary,
})
```

or direct keys pass chesthe:

```python
context.update({
    "new_customers_today": customer_summary["new_customers_today"],
    "repeat_customers_today": customer_summary["repeat_customers_today"],
    "offer_claimed_today": customer_summary["offer_claimed_today"],
    "offer_claimed_percent": customer_summary["offer_claimed_percent"],
})
```

### Why view lo modify chesam?

Template lo database queries cheyyakudadhu. Template only display kosam. Actual counts calculate chesi context through template ki pampadam clean Django pattern.

---

## 11. Template File Modified

Branch home template / right card template area:

```text
offers/templates/branch/branch_home.html
```

or right card separate partial lo unte:

```text
offers/templates/branch/partials/today_visits_card.html
```

or

```text
offers/templates/branch/partials/right_card.html
```

### What changed in template?

Old last-week / increment text block ni remove/comment chesam.

Example old idea:

```django
{# Last week increment / comparison block removed or commented #}
```

New values display chesam:

```django
{{ customer_summary.new_customers_today }}
{{ customer_summary.repeat_customers_today }}
{{ customer_summary.offer_claimed_percent }}%
```

### Why template lo modify chesam?

Right card lo branch owner/staff ki direct ga useful metrics show cheyyadaniki:

- Today new customers entha mandi?
- Today repeat customers entha mandi?
- Today visits lo entha percent offer claim ayyayi?

Last week comparison early stage lo confusing ga untundi, especially data low ga unte. Percentage card immediate actionable metric.

---

## 12. CSS / UI Changes

Right card UI lo existing classes maintain cheyyadam preferred.

Reason:
- Mobile layout break avvakudadhu.
- Existing design consistency maintain avvali.
- Other pages lo same classes reuse avutunte regression avoid avuthundi.

Changes mostly visual/content-level:

- Last week/increment text remove/comment.
- Offer claimed percentage ni clean metric ga show cheyyadam.
- Existing card spacing and right-card structure disturb cheyyakunda values replace cheyyadam.

---

## 13. Performance Notes

Important rule:

```text
Python loops avoid cheyyali. DB aggregates/subqueries use cheyyali.
```

Reason:
- Visits table future lo large avuthundi.
- Every branch dashboard open ayye sari thousands of rows Python lo loop cheyyadam slow.
- DB-level count/distinct/subquery better.

Good approach:

```python
.values("user_id").distinct().count()
```

or first-visit checks kosam:

```python
Min("created_at")
```

or advanced optimization kosam:

```python
Exists / OuterRef
```

---

## 14. Business Definitions Finalized

### New Customer

```text
A user whose first-ever visit in the current branch is today.
```

### Repeat Customer

```text
A user who visited the current branch today and also had an earlier visit in the same branch before today.
```

### Offer Claimed %

```text
Today claimed offers divided by today branch visits, multiplied by 100.
```

---

## 15. Why We Removed Last Week Increment

Last-week comparison card current stage lo reliable metric kaadu.

Problems:
- New branch / low data unte percentage weird ga kanipistundi.
- Zero previous data unte increment misleading avuthundi.
- Staff ki immediate action ivvadu.

Offer claimed percentage better because:
- Today performance directly shows.
- Visit-to-claim conversion idea ostundi.
- Branch staff ki offers working aa leda ani quick signal istundi.

---

## 16. Final Data Flow

```text
User scans QR / enters PIN
        ↓
UserVisitEvent record create avuthundi
        ↓
Offer eligibility check / claim issue avuthundi
        ↓
UserOfferClaim record create avuthundi if eligible/claimed
        ↓
Branch dashboard view loads
        ↓
get_branch_customer_summary_counts(branch) helper runs
        ↓
Counts + percentage context lo template ki pass avuthayi
        ↓
Right card lo New / Repeat / Offer Claimed % display avuthayi
```

---

## 17. Files Summary

### 1. Helper file

```text
offers/helpers/branch_customer_summary.py
```

Purpose:
- Branch-wise customer summary counts calculate cheyyadam.
- New customer, repeat customer, offer claimed percentage logic separate ga maintain cheyyadam.

### 2. View file

```text
offers/views.py
```

Purpose:
- Helper call cheyyadam.
- Returned values ni template context lo pass cheyyadam.

### 3. Template file

```text
offers/templates/branch/branch_home.html
```

or right card partial:

```text
offers/templates/branch/partials/today_visits_card.html
```

Purpose:
- Right card lo old last-week/increment section remove/comment cheyyadam.
- New customer, repeat customer, offer claimed percentage values display cheyyadam.

### 4. CSS file / style block

```text
branch home CSS / existing template style block
```

Purpose:
- Existing right card layout preserve cheyyadam.
- Mobile design disturb kakunda content update cheyyadam.

---

## 18. Final Note

Ee modification lo main focus:

```text
clean business logic + branch-wise accuracy + dashboard performance
```

No new DB table required. Existing visit and claim records enough. Helper file lo logic petti, view through context pass chesi, template lo only display cheyyadam best structure.
