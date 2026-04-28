# Branch Dashboard – Complete Technical Notes

> Updated notes file. Includes original Branch All Visits notes plus recent modifications:
> live endpoint renaming, search clear icon, history UI polish, Branch Home today customer counts, service-file split, and deployment checklist.

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

### 1.2 `branch_all_visits_table_live` API create chesam

This is our live API endpoint.

```python
def branch_all_visits_table_live(request):
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
    bviews.branch_all_visits_table_live,
    name="branch_all_visits_table_live",
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
/branch/visits/live/  # URL path can stay same; URL name/function renamed?q=mu&page=1 API call chestundi
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
branch_all_visits_table_live endpoint lo duplicate same logic
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
/branch/visits/live/  # URL path can stay same; URL name/function renamed
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
branch_all_visits_table_live(request)
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
/branch/visits/live/  # URL path can stay same; URL name/function renamed?page=2
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
---

# Recent Updates – Search Box, History UI, Branch Home Today Cards

## 1. Endpoint Naming Cleanup

We renamed vague live endpoint names to avoid future confusion.

### Old confusing names

```text
branch_all_visits_live
branch_live_api
```

### New clear names

```text
branch_all_visits_table_live
branch_today_visits_live
```

Meaning:

```text
branch_all_visits_table_live
→ All Visits page table/search/pagination AJAX update

branch_today_visits_live
→ Branch Home Today cards live update

branch_visit_history_live
→ One customer's history Load More AJAX
```

### Required search checks

Old names should not remain:

```powershell
Get-ChildItem -Recurse -File -Include *.py,*.html,*.js |
Select-String -Pattern "branch_all_visits_live|branch_live_api" |
Select-Object Path, LineNumber, Line
```

New names should appear in expected places:

```powershell
Get-ChildItem -Recurse -File -Include *.py,*.html,*.js |
Select-String -Pattern "branch_all_visits_table_live|branch_today_visits_live" |
Select-Object Path, LineNumber, Line
```

Expected:

```text
branch_all_visits_table_live:
- offers/branch_views.py
- offers/urls.py
- allvisits_record_table.html

branch_today_visits_live:
- offers/branch_views.py
- offers/urls.py
- today_visits_card.html
```

---

## 2. Search Box Clear Icon Update

### What changed

Search input lo right side small close/X icon add chesam.

Behavior:

```text
User types text
→ X icon visible
User clicks X
→ search input clear
→ table resets through AJAX
→ input focus remains
```

### Template changes

Search input wrapper:

```html
<div class="visits-search-input-wrap">
  <input
    type="text"
    name="q"
    id="visitsLiveSearch"
    class="visits-card-search__input"
    placeholder="Search by user name / email / token"
    value="{{ q }}"
    autocomplete="off"
  >

  <button
    type="button"
    id="visitsSearchClearBtn"
    class="visits-search-clear-btn"
    aria-label="Clear search"
    {% if not q %}hidden{% endif %}
  ></button>
</div>
```

Old separate `Clear` link can be removed because X icon handles reset.

### CSS

Text `×` glyph center issue avoid cheyyadaniki CSS pseudo-elements tho X draw chesam:

```css
.visits-search-clear-btn{
  position:absolute;
  right:10px;
  top:50%;
  transform:translateY(-50%);
  width:26px;
  height:26px;
  padding:0;
  border:0;
  border-radius:999px;
  background:#eef3ff;
  color:#29478f;
  cursor:pointer;
  display:inline-flex;
  align-items:center;
  justify-content:center;
}

.visits-search-clear-btn::before,
.visits-search-clear-btn::after{
  content:"";
  position:absolute;
  width:13px;
  height:3px;
  border-radius:999px;
  background:currentColor;
  left:50%;
  top:50%;
  transform-origin:center;
}

.visits-search-clear-btn::before{
  transform:translate(-50%, -50%) rotate(45deg);
}

.visits-search-clear-btn::after{
  transform:translate(-50%, -50%) rotate(-45deg);
}
```

### JS

Clear button click:

```js
if (searchClearBtn) {
  searchClearBtn.addEventListener("click", function () {
    searchInput.value = "";
    toggleSearchClearButton();
    fetchVisits(buildLiveUrlFromForm());
    searchInput.focus();
  });
}
```

---

## 3. Visit History UI Polish

### What changed

History expanded box design improved:

```text
- history box highlight added
- left accent line added
- better border/shadow
- table header/body center alignment
- claim Yes/No pill style
```

### Why

Earlier history table looked mixed with main table. Now it looks like a separate expanded detail panel.

### Important CSS ideas

```css
.visit-history-box{
  position:relative;
  background:linear-gradient(180deg, #fbfdff 0%, #eef5ff 100%);
  border:1px solid #aac0ff;
  border-radius:20px;
  padding:16px;
  box-shadow:
    0 14px 34px rgba(41, 71, 143, .14),
    inset 0 1px 0 rgba(255,255,255,.95);
  overflow:hidden;
}

.visit-history-box::before{
  content:"";
  position:absolute;
  left:0;
  top:18px;
  bottom:18px;
  width:4px;
  border-radius:0 8px 8px 0;
  background:#4f7cff;
}
```

### Header/body center alignment

Desktop table uses fixed layout and stable column widths:

```css
@media (min-width:768px){
  .visit-history-table{
    table-layout:fixed;
  }

  .visit-history-table thead th,
  .visit-history-table tbody td{
    text-align:center;
    vertical-align:middle;
  }
}
```

If other CSS overrides header alignment, final override can be added at the bottom of the style block:

```css
.visits-card .visit-history-table thead th,
.visits-card .visit-history-table tbody td{
  text-align:center !important;
  vertical-align:middle !important;
}
```

---

## 4. Only One History Table Open at a Time

### What changed

When one user history is open and staff opens another user history:

```text
new history opens
old history closes automatically
old history appended Load More rows reset
```

### Why

This keeps the UI clean and avoids multiple expanded history boxes cluttering the table.

### JS idea

```js
function closeOtherVisitHistories(activeHistoryRow) {
  const activeId = activeHistoryRow ? activeHistoryRow.id : "";

  document.querySelectorAll(".visit-history-row").forEach(function (row) {
    if (row.id === activeId) return;
    if (row.hasAttribute("hidden")) return;

    resetHistoryRow(row);
    row.setAttribute("hidden", "");
  });

  document.querySelectorAll(".expand-btn.is-open").forEach(function (otherBtn) {
    if (otherBtn.getAttribute("data-target") === activeId) return;

    otherBtn.classList.remove("is-open");
    otherBtn.setAttribute("aria-expanded", "false");
  });
}
```

---

# Branch Home – Today Customer Counts + Live Update

## 1. What changed

Branch Home Today card now uses customer-based metrics.

Cards:

```text
Total Customers
Offer Claimed
New Customers
Repeated Customers
```

Mapping:

```text
Total Customers    → total_today_customers
Offer Claimed      → today_offer_claims / offer_claims
New Customers      → new_customers
Repeated Customers → repeated_customers
```

Important: We changed first card from `Total Visits` to `Total Customers` for consistency with customer-count logic.

---

## 2. Today Customer Logic

### Formula

```text
Total Today Customers:
  Current branch lo today visit chesina unique users

New Customers:
  Today visit chesaru
  + same branch lo today mundu previous visit ledu

Repeated Customers:
  Today visit chesaru
  + same branch lo today mundu previous visit undhi
```

### Example

```text
User A first time today visited branch
→ New Customer

User B visited last week and again today
→ Repeated Customer

User C visited today morning and today evening
→ Still New Customer for today logic, because previous visit before today ledu
```

Note:
Backend lo per user per day one visit design unte today visit count and today customer count may look same. Still customer-based names and variables should be used to avoid future confusion.

---

## 3. Time Helper Usage

Common time helper:

```text
offers/services/common/time_helpers.py
```

Function:

```python
get_local_day_bounds(dt=None)
```

Purpose:

```text
day_start      → local today 12:00 AM
next_day_start → tomorrow 12:00 AM
```

Use range filters instead of `created_at__date` for better timezone safety and index usage:

```python
created_at__gte=day_start,
created_at__lt=next_day_start,
```

---

## 4. Branch Home View

`branch_home_view` still handles request/session/render. It should call service/helper functions for counts.

Important data passed to template:

```python
{
    "total_today_customers": today_customer_counts["total_today_customers"],
    "new_customers": today_customer_counts["new_customers"],
    "repeated_customers": today_customer_counts["repeated_customers"],
    "returning_rate": today_customer_counts["returning_rate"],
    "new_customer_rate": today_customer_counts["new_customer_rate"],
    "today_offer_claims": today_offer_claims,
}
```

---

# Service File Split

## 1. New service file

Created:

```text
D:\restarent_application66\offers\services\branch_api\branch_today_metrics_service.py
```

Contains:

```python
get_branch_all_time_customer_summary_counts(branch)
get_branch_today_customer_summary_counts(branch, day_start, next_day_start)
get_branch_today_visits_live_data(branch)
```

---

## 2. Function responsibilities

### `get_branch_all_time_customer_summary_counts(branch)`

Used for All Visits overview customer metrics.

Returns:

```text
total_customers
one_time_customers
repeated_customers
returning_rate
one_time_rate
```

Logic:

```text
One-time customer:
  Branch lo exactly 1 visit unna user

Repeated customer:
  Branch lo 2 or more visits unna user

Returning rate:
  repeated_customers / total_customers * 100
```

### `get_branch_today_customer_summary_counts(branch, day_start, next_day_start)`

Used for Branch Home today customer metrics.

Returns:

```text
total_today_customers
new_customers
repeated_customers
returning_rate
new_customer_rate
```

### `get_branch_today_visits_live_data(branch)`

Used by live endpoint:

```python
branch_today_visits_live
```

Returns JSON-ready today card data:

```text
visits
qr_visits
staff_verified
offer_claims
total_today_customers
new_customers
repeated_customers
returning_rate
new_customer_rate
```

Even if UI currently shows customer cards only, the extra values are available for future use.

---

## 3. Branch view import

`branch_views.py` should import:

```python
from offers.services.branch_api.branch_today_metrics_service import (
    get_branch_all_time_customer_summary_counts,
    get_branch_today_customer_summary_counts,
    get_branch_today_visits_live_data,
)
```

After importing from service, remove local duplicate definitions from `branch_views.py`:

```python
def get_branch_all_time_customer_summary_counts(...):
    ...

def get_branch_today_customer_summary_counts(...):
    ...
```

Expected: definitions should exist only inside service file.

---

## 4. Thin live view

`branch_today_visits_live` should stay in `branch_views.py` because it handles request/session/JsonResponse.

Correct slim version:

```python
@require_branch_session
def branch_today_visits_live(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    today_data = get_branch_today_visits_live_data(branch)

    return JsonResponse({
        "ok": True,
        "today": today_data,
    })
```

---

## 5. Folder structure

Required structure:

```text
offers/
├── branch_views.py
├── urls.py
├── services/
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   └── time_helpers.py
│   └── branch_api/
│       ├── __init__.py
│       └── branch_today_metrics_service.py
└── templates/
    └── branch/
        ├── branch_homepage/
        │   └── branch_homepage.html
        ├── partials/
        │   └── today_visits_card.html
        └── branch_all_visits/
            └── partials/
                └── allvisits_record_table/
                    ├── allvisits_record_table.html
                    ├── visits_meta.html
                    ├── visits_table_body.html
                    ├── visits_history_rows.html
                    └── visits_pagination.html
```

Required empty init files:

```text
offers/services/__init__.py
offers/services/common/__init__.py
offers/services/branch_api/__init__.py
```

---

# Branch Home Today Card Template

## 1. File

```text
D:\restarent_application66\offers\templates\branch\partials\today_visits_card.html
```

## 2. Card value IDs

```html
todayCustomersCount
todayOfferClaimsCount
todayNewCustomersCount
todayRepeatedCustomersCount
```

## 3. Template variables

```django
{{ total_today_customers|default:"0" }}
{{ today_offer_claims|default:"0" }}
{{ new_customers|default:"0" }}
{{ repeated_customers|default:"0" }}
```

## 4. Live JS

Add script after `</style>`:

```html
<script>
(function () {
  const endpoint = "{% url 'offers:branch_today_visits_live' %}";

  const nodes = {
    totalCustomers: document.getElementById("todayCustomersCount"),
    offerClaims: document.getElementById("todayOfferClaimsCount"),
    newCustomers: document.getElementById("todayNewCustomersCount"),
    repeatedCustomers: document.getElementById("todayRepeatedCustomersCount"),
  };

  function updateNode(node, value) {
    if (!node) return;
    node.textContent = value ?? 0;
  }

  async function refreshTodayVisitCounts() {
    try {
      const response = await fetch(endpoint, {
        method: "GET",
        headers: {
          "Accept": "application/json",
          "X-Requested-With": "XMLHttpRequest"
        },
        cache: "no-store"
      });

      if (!response.ok) return;

      const data = await response.json();
      if (!data.ok || !data.today) return;

      updateNode(nodes.totalCustomers, data.today.total_today_customers);
      updateNode(nodes.offerClaims, data.today.offer_claims);
      updateNode(nodes.newCustomers, data.today.new_customers);
      updateNode(nodes.repeatedCustomers, data.today.repeated_customers);
    } catch (error) {
      // silent fail; UI should not break
    }
  }

  refreshTodayVisitCounts();
  window.setInterval(refreshTodayVisitCounts, 10000);
})();
</script>
```

Production interval recommendation:

```text
10–15 seconds
```

Avoid too-fast polling if many branch dashboards are open.

---

# URL Routes Summary

## All Visits table live

```python
path(
    "branch/visits/live/",
    bviews.branch_all_visits_table_live,
    name="branch_all_visits_table_live",
)
```

## Visit history load more

```python
path(
    "branch/visits/history/live/",
    bviews.branch_visit_history_live,
    name="branch_visit_history_live",
)
```

## Branch Home today card live

```python
path(
    "branch/today-visits/live/",
    bviews.branch_today_visits_live,
    name="branch_today_visits_live",
)
```

---

# Performance / Deployment Notes

## 1. Live refresh load

`branch_today_visits_live` polling every 10 seconds is okay for normal usage.

Risk increases if:

```text
many branch dashboards stay open
polling interval is too low
database has large visit table without indexes
```

## 2. Recommended DB indexes later

Add indexes before large production usage:

```text
UserVisitEvent(branch, created_at)
UserVisitEvent(branch, user, created_at)
UserOfferClaim(branch, issued_at)
UserOfferClaim(visit_event)
```

Why:

```text
Today count filters use branch + created_at
New/repeated logic uses branch + user + created_at
Offer claim counts use branch + issued_at
History claim count uses visit_event
```

## 3. All Visits limits

Recommended production values:

```python
CUSTOMERS_PER_PAGE = 50
HISTORY_LIMIT_PER_USER = 30
HISTORY_PER_PAGE = 30
```

If you use `HISTORY_LIMIT_PER_USER = 20`, then set:

```python
HISTORY_PER_PAGE = 20
```

Important:

```text
HISTORY_LIMIT_PER_USER and HISTORY_PER_PAGE must match
```

Otherwise history pages can skip records.

---

# Final Updated Checklist

## Branch Home

```text
✅ Total Customers card uses total_today_customers
✅ New Customers card uses new_customers
✅ Repeated Customers card uses repeated_customers
✅ Offer Claimed card uses today_offer_claims / offer_claims
✅ Live endpoint name is branch_today_visits_live
✅ Service helper get_branch_today_visits_live_data is used
✅ JS endpoint uses {% url 'offers:branch_today_visits_live' %}
✅ JS interval set to 10–15 seconds for production
```

## All Visits

```text
✅ All Visits table endpoint name is branch_all_visits_table_live
✅ Search works with 500ms debounce
✅ Search starts from 2 characters
✅ Search clear X icon clears and resets table
✅ AJAX pagination works
✅ Meta/table/pagination partials update without full reload
✅ Only one history table should stay open at a time
✅ History Load More works
✅ Closing/reopening history resets appended rows
✅ History table UI has highlight, centered headers/data, and Yes/No claim display
```

## Service Files

```text
✅ branch_today_metrics_service.py contains count formulas
✅ time_helpers.py contains get_local_day_bounds
✅ branch_views.py stays focused on request/render/JsonResponse
✅ Duplicate local metric helper functions removed from branch_views.py
```

## Commands

Search old names:

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

Check service helper definitions:

```powershell
Get-ChildItem -Recurse -File -Include *.py |
Select-String -Pattern "def get_branch_today_customer_summary_counts|def get_branch_all_time_customer_summary_counts|def get_branch_today_visits_live_data" |
Select-Object Path, LineNumber, Line
```

Expected:
- helper definitions only in service file
- imports/usages in branch_views.py
