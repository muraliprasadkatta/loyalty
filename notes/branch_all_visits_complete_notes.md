# Branch All Visits – Complete Technical Notes


---

# Branch All Visits – Live Search + Pagination Notes

## 1. What we modified

### 1.1 `branch_all_visits` view helper-based chesam

Before:
- All logic direct ga `branch_all_visits()` view lone undedi.

Now:
```python
def build_branch_visits_context(request, branch):
    ...
```

Purpose:
- Full page view and live AJAX API rendu same logic use cheyyali.
- Future lo search/filter/pagination logic change cheyyali ante okka helper lo change chesthe enough.

---

### 1.2 `branch_all_visits_live` API create chesam

This is our live API endpoint.

```python
def branch_all_visits_live(request):
    ...
    return JsonResponse({
        "ok": True,
        "meta_html": meta_html,
        "table_body_html": table_body_html,
        "pagination_html": pagination_html,
    })
```

Purpose:
- Search box lo type chesthe page reload avvakunda table update avvali.
- API backend lo DB search chestundi.
- Rendered HTML partials return chestundi.

---

### 1.3 URL add chesam

`urls.py` lo:

```python
path(
    "branch/visits/live/",
    views.branch_all_visits_live,
    name="branch_all_visits_live",
),
```

Purpose:
- JavaScript this URL ni call chesi search results fetch chestundi.

---

### 1.4 Table template ni partials ga split chesam

Main file:

```text
allvisits_record_table.html
```

Dynamic partial files:

```text
visits_meta.html
visits_table_body.html
visits_pagination.html
```

#### `visits_meta.html`
Shows:

```text
Showing 2 of 10 users · Last updated 09:30 AM
```

#### `visits_table_body.html`
Contains:
- customer rows
- visit history hidden rows
- claims count
- latest visit details

#### `visits_pagination.html`
Contains:
- previous arrow
- current page number
- next arrow

Purpose:
- AJAX search appudu full page reload kakunda only meta + table body + pagination replace cheyyadam.

---

### 1.5 JavaScript AJAX live search add chesam

Search input lo type chesthe:

```text
500ms wait
then backend API call
then table update
```

Important logic:

```js
if (value.length === 0 || value.length >= 2) {
    fetchVisits(buildLiveUrlFromForm());
}
```

Meaning:
- 0 letters → reset full list
- 1 letter → search cheyyadu
- 2+ letters → DB search chestundi

So every character ki search cheyyadu. 2 letters minimum, and 500ms debounce untundi.

Example:

```text
m        → no search
mu       → 500ms wait → search
mur      → 500ms wait → search
murali   → 500ms wait → search
clear    → reset full list
```

If user fast ga `murali` type chesthe every letter ki request velladu. Timer reset avutundi. Usually final pause tarvatha request veltundi.

---

## 2. How it works now

Flow:

```text
User search box lo "mu" type chestadu
        ↓
JS 500ms wait chestundi
        ↓
/branch/visits/live/?q=mu&page=1 API call chestundi
        ↓
Django build_branch_visits_context() run chestundi
        ↓
DB lo all customers/search results filter chestundi
        ↓
Only current page users render chestundi
        ↓
meta_html + table_body_html + pagination_html JSON lo return
        ↓
JS old table ni replace chestundi
        ↓
Avatar colors + count formatting malli apply chestundi
```

So idi current page-only search kaadu. Database lo matching customers ni search chestundi.

---

## 3. Pagination logic

Helper lo:

```python
CUSTOMERS_PER_PAGE = 2  # testing
```

Currently testing kosam 2.

Production lo better:

```python
CUSTOMERS_PER_PAGE = 50
```

or max:

```python
CUSTOMERS_PER_PAGE = 100
```

My recommendation:
- 50 per page best starting point.

Why 300 avoid cheyyali:
- Mana row simple kaadu.
- Main user row, hidden visit history, mobile cards, claim count, avatar colors, pagination anni unnayi.
- 300 users one page lo render chesthe browser slow avvachu.

---

## 4. Server slow/down avuthadha?

Correct ga implement chesthe server down avvadu.

Protections:
1. 1 letter ki search ledu
2. 500ms debounce undi
3. old request cancel using AbortController
4. pagination limit undi
5. only current page results render chestunnam

Risk eppudu:
- every keypress DB call
- pagination lekunda all matching users render
- all visits load at once

Manam ala cheyyaledu.

---

## 5. Search results lo first page only

Example:

```text
Search: "mu"
Matching customers: 143
CUSTOMERS_PER_PAGE = 50
```

Then:

```text
Page 1 → first 50 matching users
Page 2 → next 50
Page 3 → remaining 43
```

Correct flow:

```text
All customers
→ q filter
→ matching customers
→ paginate
→ current page display
```

So search filter first, pagination next.

---

## 6. What helper does

`build_branch_visits_context(request, branch)` handles:

```text
q search
method filter
date filter
total visits
today visits
unique users
qr pin visits
total claims
customer-wise grouping
pagination
claim count per visit
masked email
latest visit
all visits history per visible user
```

It returns context:

```python
{
    "branch": branch,
    "visits": visits,
    "total_visits": total_visits,
    "today_visits": today_visits,
    "unique_users": unique_users,
    "qr_pin_visits": qr_pin_visits,
    "total_claims": total_claims,
    "q": q,
    "method": method,
    "date": date_str,
    "page_obj": page_obj,
}
```

---

## 7. Why helper created?

Without helper:

```text
branch_all_visits view lo one logic
branch_all_visits_live API lo duplicate same logic
```

That is bad.

Because future lo bug fix chesthe two places lo update cheyyali.

With helper:

```text
normal page and live API both same helper use chestayi
```

So one source of truth.

---

## 8. Why API created?

Normal `branch_all_visits` full page render chestundi.

But live search ki full page reload avvakudadhu.

So new API:

```text
/branch/visits/live/
```

only table dynamic HTML return chestundi.

It returns:

```text
meta_html
table_body_html
pagination_html
```

JS simply replace chestundi.

---

## 9. Why partial files created?

To avoid huge JS HTML strings.

Bad way:

```text
JS lo table rows build cheyyadam
```

Future lo design change chesthe JS and Django template rendu update cheyyali.

Good way:

```text
Django partials render chestundi
JS only replace chestundi
```

So future modification easy:

```text
meta issue → visits_meta.html
row issue → visits_table_body.html
pagination issue → visits_pagination.html
search/query issue → build_branch_visits_context()
AJAX issue → script fetchVisits()
```

---

## 10. Current production values suggestion

Testing:

```python
CUSTOMERS_PER_PAGE = 2
```

Production:

```python
CUSTOMERS_PER_PAGE = 50
```

Heavy branch, good server:

```python
CUSTOMERS_PER_PAGE = 100
```

Avoid:

```python
CUSTOMERS_PER_PAGE = 300
```

unless really needed and tested.

---

## 11. Final status

```text
✅ All Visits table is now paginated
✅ Search works across all pages/customers
✅ Live AJAX search works without full page reload
✅ Search starts from 2 characters
✅ Clear/reset works
✅ Pagination works with AJAX
✅ Query logic centralized in helper
✅ Dynamic HTML split into partials
✅ Server load controlled with debounce + pagination
```

Simple summary:

```text
Manam table ni professional server-side live search system ga marcham.
Search frontend lo local rows meeda kaadu; backend DB lo search chestundi.
But all matching data load cheyyadu; pagination tho safe ga first page results matrame show chestundi.
```


---

# Branch All Visits – History Load More Notes

## 1. What we modified

We improved the **Visit History expand section** inside the Branch All Visits table.

Before:
- Each user row had hidden visit history.
- If one user had many visits, all visits were loaded/rendered inside the hidden row.
- Even if staff did not open the history, backend and browser still carried that hidden HTML.
- After clicking Load More, closing and reopening the same user history kept the appended rows until refresh.

Now:
- Initial expand history shows only limited latest visits.
- Older visits are loaded only when staff clicks **Load more**.
- Closing the history resets it back to the initial latest rows.
- Reopening history starts clean again.

---

## 2. Why we did this

Main reason: performance and clean UX.

If one customer has many visits:

```text
Customer A = 200 visits
Customer B = 100 visits
Customer C = 150 visits
```

Old logic would render a lot of hidden rows. That can make:

```text
page load slow
AJAX response heavy
browser DOM heavy
mobile UI laggy
```

New logic keeps page light:

```text
Initial render → latest 20 visits only
Load More → next 20 visits only when needed
Close → reset back to initial state
```

---

## 3. Files involved

### 3.1 View file

```text
D:\restarent_application66\offers\branch_views.py
```

Used for:
- main All Visits page context
- live table search API
- user visit history Load More API

Important functions:

```python
build_branch_visits_context(request, branch)
branch_all_visits_live(request)
branch_visit_history_live(request)
branch_all_visits(request)
```

---

### 3.2 Main table wrapper template

```text
D:\restarent_application66\offers\templates\branch\branch_all_visits\partials\allvisits_record_table\allvisits_record_table.html
```

Used for:
- search box
- table wrapper
- pagination wrapper
- CSS
- JavaScript
- AJAX live search
- AJAX pagination
- Load More click handling
- close/reopen history reset

---

### 3.3 Main table body partial

```text
D:\restarent_application66\offers\templates\branch\branch_all_visits\partials\allvisits_record_table\visits_table_body.html
```

Used for:
- user rows
- expand button
- hidden visit history box
- initial visit history table
- Load More button

---

### 3.4 History rows partial

```text
D:\restarent_application66\offers\templates\branch\branch_all_visits\partials\allvisits_record_table\visits_history_rows.html
```

Used for:
- rendering visit history table rows
- used both in initial page render and Load More API response

This avoids duplicate row HTML in multiple templates.

---

### 3.5 Meta partial

```text
D:\restarent_application66\offers\templates\branch\branch_all_visits\partials\allvisits_record_table\visits_meta.html
```

Used for:
- “Showing X of Y users · Last updated …”

---

### 3.6 Pagination partial

```text
D:\restarent_application66\offers\templates\branch\branch_all_visits\partials\allvisits_record_table\visits_pagination.html
```

Used for:
- main customer pagination
- previous/next page buttons
- AJAX pagination

---

### 3.7 URL file

```text
D:\restarent_application66\offers\urls.py
```

Used for:
- registering the Load More history API route

New URL:

```python
path(
    "branch/visits/history/live/",
    views.branch_visit_history_live,
    name="branch_visit_history_live",
)
```

---

## 4. Backend changes

### 4.1 `build_branch_visits_context()`

We added:

```python
CUSTOMERS_PER_PAGE = 50
HISTORY_LIMIT_PER_USER = 20
```

Purpose:
- `CUSTOMERS_PER_PAGE` controls how many customers show per main table page.
- `HISTORY_LIMIT_PER_USER` controls how many visit history rows show initially inside expand.

Testing value can be:

```python
HISTORY_LIMIT_PER_USER = 1
```

or:

```python
HISTORY_LIMIT_PER_USER = 2
```

Production recommended:

```python
HISTORY_LIMIT_PER_USER = 20
```

---

### 4.2 Initial history is now limited

Before:

```python
grouped[key]["all_visits"].append(visit)
```

This kept appending all visits.

Now:

```python
if len(grouped[key]["all_visits"]) < HISTORY_LIMIT_PER_USER:
    grouped[key]["all_visits"].append(visit)
else:
    grouped[key]["has_more_history"] = True
```

Meaning:
- first 20 visits stored in `all_visits`
- if more visits exist, `has_more_history=True`
- template shows Load More button

---

### 4.3 New API: `branch_visit_history_live()`

This API loads more history for one user.

URL example:

```text
/branch/visits/history/live/?user_id=12&history_page=2
```

Response:

```json
{
  "ok": true,
  "history_html": "...",
  "has_next": true,
  "next_page": 3
}
```

Purpose:
- Load More button calls this API.
- API returns only next history rows, not full page.
- JavaScript appends returned rows into the existing history table.

---

## 5. Template changes

### 5.1 `visits_history_rows.html`

This partial renders each visit row:

```django
{% for visit in history_visits %}
  <tr>
    <td>{{ visit.created_at|date:"h:i A" }}</td>
    <td>{{ visit.created_at|date:"d M Y" }}</td>
    <td>{{ visit.get_visit_method_display }}</td>
    <td>
      {% if visit.staff_name %}
        {{ visit.staff_name }}
        {% if visit.staff_code %}({{ visit.staff_code }}){% endif %}
      {% elif visit.desk %}
        {{ visit.desk }}
      {% else %}
        —
      {% endif %}
    </td>
    <td>
      {% if visit.claim_count %}
        Yes
      {% else %}
        No
      {% endif %}
    </td>
  </tr>
{% endfor %}
```

Important change:
- Offer Claimed column now shows only `Yes` or `No`.
- We removed count like `Yes (1)` because main row already has claim count.

---

### 5.2 `visits_table_body.html`

History table now uses the partial:

```django
<tbody
  id="visitHistoryBody-{{ item.user.id }}"
  data-history-body
>
  {% include "branch/branch_all_visits/partials/allvisits_record_table/visits_history_rows.html" with history_visits=item.all_visits %}
</tbody>
```

Why `data-history-body`?

JavaScript uses this to capture initial rows and reset history on close.

---

### 5.3 Load More button

Added under history table:

```django
{% if item.has_more_history and item.user %}
  <div class="visit-history-more">
    <span>
      Showing latest {{ item.history_limit }} of {{ item.total_visits }} visits.
    </span>

    <button
      type="button"
      class="visit-history-load-more"
      data-history-load-more
      data-user-id="{{ item.user.id }}"
      data-next-page="2"
      data-target-body="visitHistoryBody-{{ item.user.id }}"
    >
      Load more
    </button>
  </div>
{% endif %}
```

Purpose:
- Shows only if the user has more history than initial limit.
- `data-user-id` tells API which user history to load.
- `data-next-page` starts from page 2 because page 1 is already rendered initially.
- `data-target-body` tells JS where to append new rows.

---

## 6. JavaScript changes

### 6.1 Main table live search still works

Search input behavior:

```text
0 letters → reset list
1 letter  → no search
2+ letters → live DB search after 500ms
```

This protects server from too many requests.

---

### 6.2 Main table pagination still works

Clicking main table page arrows calls:

```text
/branch/visits/live/?page=2
```

and replaces:

```text
meta_html
table_body_html
pagination_html
```

---

### 6.3 Load More click handling added

When staff clicks Load More:

```text
Get user_id
Get next history page
Call /branch/visits/history/live/
Append returned rows into tbody
Update button next page
Disable button if all visits loaded
```

Flow:

```text
Initial expand → latest 20
Load more → next 20 append
Load more → next 20 append
Last page → button says All visits loaded
```

---

### 6.4 Close/reopen reset logic added

Problem:
- Load More appended rows stayed even after closing/reopening history.

Fix:
- On page load, JS captures initial history HTML:

```js
captureInitialHistoryState(document);
```

- On AJAX table replace, it captures again:

```js
captureInitialHistoryState(document);
```

- On close, it resets history:

```js
resetHistoryRow(historyRow);
```

So now:

```text
Open history
Load more
Close history
Reopen history
→ back to initial latest rows only
```

This avoids stale expanded history staying until refresh.

---

## 7. Important constants must match

In `build_branch_visits_context()`:

```python
HISTORY_LIMIT_PER_USER = 20
```

In `branch_visit_history_live()`:

```python
HISTORY_PER_PAGE = 20
```

These two values should be the same.

If testing:

```python
HISTORY_LIMIT_PER_USER = 1
HISTORY_PER_PAGE = 1
```

If production:

```python
HISTORY_LIMIT_PER_USER = 20
HISTORY_PER_PAGE = 20
```

Why important?

If initial limit is 1 but API page size is 20:
```text
initial shows visit 1
Load More page 2 starts from visits 21-40
visits 2-20 get skipped
```

So both values must match.

---

## 8. Server benefit

Before:
- Hidden history rows could become very large.
- One user with 500 visits could make page heavy.
- Main AJAX search response could become large.

After:
- Initial page loads only limited history rows.
- Old visits are fetched only when staff clicks Load More.
- Browser DOM stays lighter.
- Mobile performance improves.
- Server work is spread across smaller requests.

---

## 9. UX behavior now

Example:

```text
User: Dhanu
Total Visits: 4
HISTORY_LIMIT_PER_USER = 1
```

Initial expand:

```text
Visit History (4)
1 latest visit row
Showing latest 1 of 4 visits
Load more
```

Click Load More:

```text
2nd visit appends
Load more remains if more exists
```

Final click:

```text
All visits loaded
```

Close row:

```text
history closes
extra loaded rows reset
button resets to Load more
```

Reopen row:

```text
only initial latest row shows again
```

---

## 10. Final result

We added a scalable two-level data loading system:

```text
Level 1:
Main table pagination
→ controls customer list

Level 2:
Visit history Load More
→ controls one customer's visit history
```

This is better than loading everything at once.

Final benefits:

```text
✅ Faster initial page load
✅ Cleaner AJAX response size
✅ No huge hidden history rows
✅ Staff can still access older visits
✅ Load More works without full page reload
✅ Closing/reopening resets history cleanly
✅ Offer Claimed column now shows only Yes/No
```

---

## 11. Quick checklist

Before testing, confirm:

```text
branch_views.py
✅ branch_visit_history_live exists
✅ HISTORY_LIMIT_PER_USER and HISTORY_PER_PAGE match

urls.py
✅ branch/visits/history/live/ route exists

visits_table_body.html
✅ tbody has data-history-body
✅ Load More button has data-history-load-more
✅ data-target-body matches tbody id

visits_history_rows.html
✅ renders history rows
✅ Offer Claimed shows Yes/No

allvisits_record_table.html
✅ JS has Load More click handler
✅ JS has resetHistoryRow
✅ JS calls captureInitialHistoryState after initial load and after AJAX replace
```
