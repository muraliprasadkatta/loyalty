# OfferZone — All Branches Page Optimization Notes
C:\Users\mural\Downloads\OfferZone_All_Branches_Optimization_Notes.md
## 1. Main files modified

### File 1
`offers/user_views.py`

Main functions touched:
- `get_bounding_box()`
- `get_latest_user_location()`
- `get_home_branch_list_card_data()`
- `user_all_branches_view()`

### File 2
`offers/templates/user_interface/user_homepage/partials/branch_all_list.html`

Main template changes:
- Search box
- Location filter
- Result meta
- Branch grid
- Load More button
- AJAX append scripts
- Search clear reset script

### File 3
`offers/templates/user_interface/user_homepage/partials/all_branch_card_append.html`

Purpose:
- AJAX Load More lo newly fetched branch cards render cheyyadaniki partial.

### File 4
`offers/models.py`

Model touched:
- `Branch`

Added/confirmed index:
```python
models.Index(fields=["latitude", "longitude"], name="idx_branch_lat_lon")
```

Purpose:
- DB lo nearby latitude/longitude range filter fast ga avvadam.

---

## 2. Why these changes were needed

Earlier All Branches page lo issues:
1. Load More click chesthe page top ki velladam / bad UX.
2. `visible=12,24,36` style lo old data repeat ga process avuthundhi.
3. Near me filter lo all branches teeskoni Python lo distance calculate chesthunna logic heavy avvachu.
4. Search too broad ga `location_subtitle` kuda scan chesthundhi.
5. Location saved unte nearest branches top lo ravali.
6. Location not saved unte page empty avvakudadhu; normal all branches ravali.

Goal:
- User ki smooth Load More experience ivvali.
- Server unnecessary work tagginchali.
- Nearby filtering fast ga undali.
- Search cleaner ga undali.
- Location optional ga undali.

---

## 3. Template changes — `branch_all_list.html`

### Search box added

Search box added for:
- branch name
- display title
- area/city short title

Template input:
```html
<input
  type="search"
  id="branchSearchInput"
  name="q"
  class="branch-search-input"
  placeholder="Search branch, area, city..."
  value="{{ q|default:'' }}"
  autocomplete="off"
>
```

Purpose:
- User branch/area/city search cheyyadaniki.

### Location filter added

Dropdown:
```html
<select
  id="branchLocationFilter"
  name="location"
  class="branch-location-filter"
>
  <option value="">Location</option>
  <option value="nearby">Near me</option>
  <option value="active">Active offers</option>
  <option value="all">All branches</option>
</select>
```

Purpose:
- `Near me` → saved current location base ga 50km filter.
- `Active offers` → only offer active branches.
- `All branches` → normal all branches.

### Result meta added

Shows:
- Showing 12 of 120 branches
- Within 50 km
- Search: “kukatpally”

Template block:
```django
<div class="branch-result-meta">
  Showing {{ loaded_count }} of {{ branch_count }} branches

  {% if is_nearby_mode %}
    <span>• Within {{ nearby_radius_km }} km</span>
  {% endif %}

  {% if q %}
    <span>• Search: “{{ q }}”</span>
  {% endif %}
</div>
```

Purpose:
- User ki current data state clear ga chupinchadam.

### Branch grid made stable

Grid always exists now:
```django
<div id="branchGrid" class="br-grid">
  {% if branch_count %}
    {% include "user_interface/user_homepage/partials/all_branch_card_append.html" with branches=branches %}
  {% endif %}
</div>
```

Purpose:
- Search no-results tarvatha clear chesthe AJAX reset work avvali.
- Old issue: no results appudu `branchGrid` render kakapothe reset script stop ayyedi.

### Empty message added

```django
<div id="branchEmptyMsg" class="msg" {% if branch_count %}hidden{% endif %}>
  No branches yet.
</div>
```

Purpose:
- No data state clean ga handle cheyyadaniki.

### Load More changed to offset-based

Button:
```django
<button
  type="button"
  id="branchLoadMoreBtn"
  class="branch-load-more-btn"
  data-next-offset="{{ next_offset }}"
  data-q="{{ q|default:'' }}"
  data-location="{{ location|default:'' }}"
>
  Load more
</button>
```

Earlier:
```text
visible=12
visible=24
visible=36
```

Now:
```text
offset=0
offset=12
offset=24
```

Purpose:
- Load more click appudu next batch identify cheyyadaniki.

---

## 4. JavaScript changes

### Location filter change script

When filter changes:
- Search input clear
- Offset reset to 0
- Form submit

Purpose:
- Filter change appudu old offset/search state mix avvakunda.

### Search clear reset script

If user search box clear chesthe:
- `q` remove
- `visible` remove
- `offset=0`
- AJAX fetch
- Grid reset with all branches
- Load More button reset
- URL clean

Purpose:
- Search clear chesthe page refresh compulsory kakunda data reset avvali.

### Load More script

Current logic:
```text
Click Load More
→ request offset=12 / 24 / 36
→ backend returns new cards HTML
→ grid.insertAdjacentHTML("beforeend", data.html)
→ old cards remain
→ new cards append
```

Purpose:
- User scroll position disturb kakunda old cards clickable gaane undi, new cards kindha add avvali.

Important:
```text
grid.innerHTML = data.html vaddu for Load More.
insertAdjacentHTML("beforeend", ...) use cheyyali.
```

---

## 5. Partial file — `all_branch_card_append.html`

This partial renders each branch card.

It handles:
- Branch title/location title
- Active/no offer pill
- Offer title
- Distance display
- Offer image
- Fallback no image
- Offer date

Distance display:
```django
{% if b.distance_km %}
  <div class="br-distance">
    📍 {{ b.distance_km }} km away
  </div>
{% endif %}
```

Purpose:
- AJAX Load More lo only new branch card HTML return cheyyadaniki.

---

## 6. View changes — `user_all_branches_view`

Current purpose:
- All Branches page render
- AJAX Load More response

Main logic:
```python
LOAD_STEP = 12
offset = int(request.GET.get("offset") or 0)

branch_card_data = get_home_branch_list_card_data(
    limit=LOAD_STEP,
    offset=offset,
    q=q,
    location=location,
    user=request.user,
)
```

Then:
```python
loaded_count = offset + len(branches)
has_more = loaded_count < branch_count
next_offset = loaded_count
```

AJAX response:
```python
return JsonResponse({
    "ok": True,
    "html": html,
    "loaded_count": loaded_count,
    "branch_count": branch_count,
    "has_more": has_more,
    "next_offset": next_offset,
})
```

Purpose:
- Load More button ki next offset ivvadam.
- AJAX lo only card partial HTML pampadam.

---

## 7. Helper changes — `get_home_branch_list_card_data`

This is the main function.

Current responsibilities:
- Search filter
- Nearby bounding box filter
- Offer attach
- Distance calculation
- Active offer filter
- Nearby exact 50km filter
- Sorting
- Final offset slice
- Return data for template

### Offset parsing

```python
try:
    offset = int(offset or 0)
except (TypeError, ValueError):
    offset = 0
offset = max(0, offset)
```

Purpose:
- Bad offset values vachi crash avvakunda.

### Limit parsing

```python
if limit is not None:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 12
    limit = max(1, limit)
```

Purpose:
- Load step safe ga undadaniki.

---

## 8. Search logic

Current search fields:
```python
if q:
    branches_qs = branches_qs.filter(
        Q(name__icontains=q)
        | Q(display_title__icontains=q)
        | Q(location_title__icontains=q)
    )
```

Removed:
```python
location_subtitle__icontains=q
```

Why removed:
- `location_subtitle` street/landmark detail.
- Longer field.
- Search broad avuthundhi.
- Server work konchem ekkuva.
- Results less clean.

Now search covers:
- `name` → backend branch name
- `display_title` → restaurant/branch display title
- `location_title` → area/city title

This makes search cleaner and lighter.

---

## 9. Location logic

### If current location saved

`get_latest_user_location(user)` latest `UserLocationPing` row teesukuntundhi.

Then default All Branches:
```text
All branches show avuthayi.
50km filter apply kaadhu.
But active branches first + nearest-first order.
Distance show avuthundhi.
```

Example:
```text
/user/branches/
→ all branches
→ saved location unte nearest branches top lo
```

Important:
- Default all branches lo 50km limit ledu.
- Only sorting lo location use chestham.

### If current location not saved

Then:
```text
user_coords = None
```

Behavior:
- Home page branch cards show avuthayi.
- All Branches page show avuthundhi.
- Search works.
- Distance show kaadhu.
- Nearest-first sorting apply kaadhu.
- Active offers first, inactive next.

So location optional. Page empty avvadhu.

### If Near me selected and location saved

Flow:
```text
User saved location
→ bounding box calculate
→ DB rough lat/lon filter
→ exact distance calculate
→ <= 50km branches only
→ active-first + nearest-first sort
```

### If Near me selected and location not saved

Behavior:
```text
Nearby filter cannot calculate.
Warning: Location not saved yet. Use current location first.
```

No crash.

---

## 10. Bounding box logic

Function:
```python
def get_bounding_box(lat, lon, radius_km):
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))

    return {
        "min_lat": lat - lat_delta,
        "max_lat": lat + lat_delta,
        "min_lon": lon - lon_delta,
        "max_lon": lon + lon_delta,
    }
```

Meaning:
- Bounding box is not a DB table.
- Bounding box is just 4 numbers:
  - `min_lat`
  - `max_lat`
  - `min_lon`
  - `max_lon`

Old method:
```text
DB nunchi all branches teeskoni
Python lo every branch distance calculate
then 50km filter
```

New method:
```text
DB ki mundhe latitude/longitude range condition istam
DB rough nearby branches matrame pampisthundhi
Python exact distance final filter chesthundhi
```

DB filter:
```python
branches_qs = branches_qs.filter(
    latitude__isnull=False,
    longitude__isnull=False,
    latitude__gte=box["min_lat"],
    latitude__lte=box["max_lat"],
    longitude__gte=box["min_lon"],
    longitude__lte=box["max_lon"],
)
```

Why exact distance still needed:
- Bounding box square/range.
- Nearby radius circle.
- Box lo konni 50km kanna bayata branches ravachu.
- So final exact distance check compulsory.

Final exact filter:
```python
branches = [
    b for b in branches
    if b.distance_km is not None and b.distance_km <= NEARBY_RADIUS_KM
]
```

Current helper applies bounding box only for:
```text
location == "nearby"
search empty
user location exists
```

So search global ga remains unaffected.

---

## 11. Distance calculation

Function:
```python
calculate_distance_km(lat1, lon1, lat2, lon2)
```

Purpose:
- User saved location nunchi branch latitude/longitude varaku exact distance calculate cheyyadam.

Distance assigned:
```python
b.distance_km = calculate_distance_km(
    user_lat,
    user_lon,
    b.latitude,
    b.longitude,
)
```

Used for:
- Distance display
- Nearest-first sorting
- Nearby exact 50km filter

---

## 12. Sorting logic

### Near me mode

```python
branches.sort(
    key=lambda b: (
        not bool(getattr(b, "offer_start", None)),
        b.distance_km if b.distance_km is not None else 999999,
        b.name.lower(),
    )
)
```

Meaning:
- Active offers first
- Nearest first
- Name fallback

### Default All Branches with saved location

Same sort:
- Active offers first
- Nearest first
- Name fallback

But:
- No 50km filtering.
- All branches still show.

### No location / search / active fallback

```python
active_branches = [b for b in branches if b.offer_start]
inactive_branches = [b for b in branches if not b.offer_start]
branches = active_branches + inactive_branches
```

Meaning:
- Active offer branches first.
- Inactive/no offer branches after.

---

## 13. Final slicing

After all filtering/sorting:

```python
branch_count = len(branches)

if limit is not None:
    branches = branches[offset:offset + limit]
```

Purpose:
- Template ki only requested batch pampadam.
- Load More lo next 12 cards return avvadam.

Important:
- Early DB slice cheyyaledu.
- Reason: offer attach, distance, active-first sorting after query jarugutunnayi.
- Early slice pedithe wrong order/results ravachu.

---

## 14. Branch model DB index

In `Branch.Meta`:

```python
indexes = [
    models.Index(
        Lower("name"),
        name="idx_branch_name_lower",
    ),
    models.Index(
        fields=["latitude", "longitude"],
        name="idx_branch_lat_lon",
    ),
]
```

Purpose of latitude/longitude index:
- Near me bounding box filter fast avvadam.
- DB latitude/longitude range matching rows quicker ga find cheyyadam.

Without index:
- DB may scan all branch rows.

With index:
- DB lat/lon range ki faster shortcut use cheyyachu.

Need migration after model change:
```powershell
python manage.py makemigrations offers
python manage.py migrate
```

---

## 15. Server slow avvakunda what we did

### Done 1 — Load More offset flow

Before:
```text
visible=12
visible=24
visible=36
```

Issue:
- Backend first 24/36 prepare chesi then new part slice.

Now:
```text
offset=0
offset=12
offset=24
```

Benefit:
- AJAX response next batch concept clear.
- Old cards remain.
- New cards append.
- Page top jump issue solved.

### Done 2 — Near me bounding box

Before:
```text
All branches fetch
All branches distance calculate
Then 50km filter
```

Now:
```text
DB rough lat/lon filter first
Only shortlisted nearby branches Python ki
Exact distance final filter
```

Benefit:
- Near me mode server work taggutundhi.

### Done 3 — Latitude/longitude DB index

Added/confirmed:
```python
models.Index(fields=["latitude", "longitude"], name="idx_branch_lat_lon")
```

Benefit:
- DB bounding box filter faster.

### Done 4 — Search simplified

Removed:
```python
location_subtitle__icontains=q
```

Kept:
- `name`
- `display_title`
- `location_title`

Benefit:
- Search less broad.
- Cleaner results.
- Less DB work.

---

## 16. What is still pending for future

### Full DB-level pagination

Current helper still does:
```text
filtered queryset → list
attach offer/distance
sort
then slice
```

Future large scale 10k+ branches ki:
```text
DB itself should return only required 12 rows.
```

But direct early slice wrong because current ordering depends on:
- Active offer status
- Distance
- Nearby exact filter
- Offer attach

So future refactor should be mode-wise:
- Default all branches → DB pagination
- Search → DB pagination
- Near me → DB-level distance/order or PostGIS
- Offer data → only paginated branch IDs ki attach

Not needed now.

### Search city/area normalized fields

Later:
```python
city = models.CharField(..., db_index=True)
area = models.CharField(..., db_index=True)
```

Benefit:
- City/area exact search faster.
- Search ranking cleaner.

Not needed now.

### Nearby locations section

Future UX idea:
```text
Search: Kukatpally

Kukatpally branches
2 found

Nearby locations within 25 km
Miyapur — 30 branches
KPHB — 12 branches
Nizampet — 8 branches
```

This should be separate section, not mixed with exact search results.

Not implemented now.

### Last visited branch fallback

Future idea:
```text
If browser location not saved:
use last confirmed UserVisitEvent branch coords as fallback.
```

But do not store it as `UserLocationPing`.

Label should be:
```text
km from your last visited area
```

Not implemented now.

---

## 17. Final current behavior summary

### `/user/branches/` with saved location

```text
All branches show.
Active offers first.
Within active/inactive groups nearest first.
Distance shown.
No 50km limit.
```

### `/user/branches/` without saved location

```text
All branches show.
Active offers first.
Inactive next.
Distance hidden.
No nearest-first sorting.
```

### `/user/branches/?location=nearby`

With saved location:
```text
Only exact 50km branches.
Bounding box first.
Exact distance final.
Active-first + nearest-first.
```

Without saved location:
```text
Warning shown.
Nearby cannot calculate.
```

### `/user/branches/?location=active`

```text
Only active offer branches.
```

### `/user/branches/?q=kukatpally`

Searches:
- `name`
- `display_title`
- `location_title`

Does not search:
- `location_subtitle`

### Load More

```text
First page offset=0
Load more offset=12
Next offset=24
Old cards stay clickable.
New cards append below.
```

---

## 18. Git commit note

Suggested commit:

```bash
git add .
git commit -m "Optimize all branches search load more and nearby filtering"
```

Current version present scale ki okay. 10k+ branches real ga vachaka full DB-level pagination and DB-level distance ordering refactor cheyyali.
