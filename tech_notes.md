## Root Router
________________________________
- **File:** `offers/views_root.py`
________________________________

- **Purpose:** App root (`/`) hit ayinappudu user ni correct destination ki redirect cheyyadam
- **Type:** Entry routing / redirect controller

### Current routing rules
1. Branch session (`branch_id`) unte → `offers:branch_home`
2. Authenticated admin user unte → `offers:admin_home`
3. Authenticated normal user unte → `offers:user_home`
4. Anonymous + `?role=branch` unte → `offers:branch_login`
5. Anonymous + `?role=admin` unte → `offers:admin_login`
6. Default fallback → `offers:user_home`

### `_safe_next()` use
- `next` URL ni validate chestundi
- unsafe external redirect ni block chestundi

### Check this file when
- root URL routing wrong ga unte
- app open ayinappudu wrong page ki velthe
- role-based redirect issue unte
- `next` param problem unte
- session-based first redirect bug unte

### Usually not needed for
- OTP logic
- UI/template issues
- internal page business logic
- mail sending
- offer/visit processing

-------------------------------------


## Signals
______________________________________

- **File:** `offers/signals.py`
______________________________________
- **Type:** Auto-triggered background logic
- **Direct URL file kaadu**
- **Direct view file kuda kaadu**

### What this file does
This file Django signals valla automatic ga run avutundi.

#### Current uses
1. **New user create ayithe**
   - auto `Profile` create chestundi

2. **Successful login ayithe**
   - auto `LoginVisit` create chestundi
   - IST date basis meeda 1 day ki 1 row matrame maintain chestundi

---

### When to check this file
`signals.py` ni mainly ee situations lo check cheyali:

- user creation / signup flow touch chesthe
- login flow touch chesthe
- OTP verify success login flow touch chesthe
- successful auth tarvata unexpected DB row create avtunte
- `Profile` auto create issue vaste
- `LoginVisit` auto create / duplicate / missing problem vaste
- "idhi ekkada nundi create ayyindi?" ani hidden flow doubt vaste

---

### When NOT to check this file usually
Ee cases lo default ga `signals.py` chudalsina avasaram undadu:

- normal URL rename
- static page route change
- template text change
- CSS / JS UI change
- dashboard rendering issue
- normal fetch endpoint change with no login/signup side effect

---

### Touch this file only if
- new signal add cheyyali
- existing signal logic modify cheyyali
- auto create ayye Profile behavior change cheyyali
- login stamp logic change cheyyali
- timezone/day-based login tracking logic change cheyyali
- login side effect disable/extend cheyyali

---

### Current dependency awareness
Ee file indirect ga auth/login flows ki related:

- user create ayye place
- `login(...)` success ayye flows
- OTP verify success ayyi login complete ayye flows

So auth-related files modify chesthe, ee file ni awareness tho check cheyyali.

---

### Main purpose summary
`offers/signals.py` =  
manual ga view nundi call cheyyakunda,  
Django event jariginappudu automatic ga run ayye background side-effect file.

---

### Simple rule
- **Signup/User create issue** → check `signals.py`
- **Login success side effect issue** → check `signals.py`
- **Random URL issue** → usually no need to check `signals.py`

---

### One-line memory note
If a change can affect **user creation**, **successful login**, or **auto DB side effects**, check `offers/signals.py`.

-----------------------------------------------------------------


## OTP Module
______________________________________

### Core Utility File
`offers/services/auth/otp_utils.py`
______________________________________

e file user login form ki and branch login ki common gause chestunnam 

### Linked Files
- `offers/user_views.py`
- `offers/branch_views.py`

### Purpose
OTP send / verify related shared helper logic.

### Debug Rule
If any OTP-related issue comes, always check these files together:
- `offers/services/auth/otp_utils.py`
- `offers/user_views.py`
- `offers/branch_views.py`

### Check Points
- OTP generate logic
- OTP send trigger point
- OTP verify flow
- Expiry / cooldown
- Error handling
- User flow vs Branch flow differences

---------------------------------------------------------------


## API Guard JS
______________________________________
### File
`offers/static/offers/js/api-guard.js`
______________________________________
### Current Usage
Ippativaraku ee file ni **branch login form** varaku matrame link chesamu.

### Connected Area
- Branch Login Form

### Note
Future lo API request validation / request safety / common fetch guard places lo kuda use cheyyachu.
Currently branch login flow lo matrame connected undi.

still pendingto connectto another form like user login form


---------------------------------------------------------------

Added shared button loading stylesheet at:
_________________________________________________

offers/static/offers/css/ui/button_loading.css
(offers/static/offers/js/ui/button_loading.js)
D:\restarent_application66\offers\templates\ui_states\spinners\button_loading.html
_________________________________________________

e file commog ga rasi spinner ga anniki temple lo kiattach chestunnam 
Purpose:
This file contains reusable CSS for button loading states across auth/login flows.
It is used to show spinner-based loading feedback, hide/show button text properly,
and keep loading buttons visually consistent across pages.

Currently linked / intended for:
- User login
- Branch login
- Admin login

Reason:
Instead of duplicating spinner/loading button CSS inside each template, a common UI stylesheet
is used so all login pages follow the same behavior and appearance.


____________________________________________________________

<script src="{% static 'offers/js/ui/interaction_blocker.js' %}"></script>
<link rel="stylesheet" href="{% static 'offers/css/ui/interaction_blocker.css' %}">
<div id="ozInteractionBlocker" hidden aria-hidden="true"></div>


e file valla use enti ante idi oka blocker lantidhi 
asalu endhuku ante e blocker anedhi suppose oka spuner anedhi run avautundhi ante appudu migatah ancor links lantivi kaniinka emina unte kani vatini temperay ga block cheyataniki use avuthaya
so dhenini prsent home page lo link chesam 
and dhenikisam ok  e link (id="ozInteractionBlocker) e linnk pettali mandataory gaaa page lo kavali anate aa page lo 
present e link ni scan to qr ane button ki add chesanu user home page lo 

_______________________________________________________________

<script src="{% static 'offers/js/ui/inline_loading.js' %}"></script>
D:\restarent_application66\offers\static\offers\css\ui\inline_loading.css
D:\restarent_application66\offers\templates\ui_states\spinners\inline_loading.html

e file anedhiinline lo spin kosam use avutudhi ante edina ok click valla modal open avvalsi unte a modal open avataniki time padutuhdinate e file ni conncet chesukovali mava

________________________________________________________________



D:\restarent_application66\offers\templates\ui_states\errors\global_toast.html
single templatelo neni css and js and html structure undhi 

dhenini universal network error ga design chesi ok pop up la pettataniki design chesam so idi inline network tho kakudna universal network error ni ok pop la chudpiatnki use avuudhi
ekkadithe api guard linkundho akkda mandatoryavuudhi 

e file in direat ga kuda api guard ki link ayi undhi 

________________________________________________________________

D:\restarent_application66\offers\static\offers\css\ui\page_loading.css D:\restarent_application66\offers\static\offers\js\ui\page_loading.js 
{% include "ui_states/spinners/page_loader.html" %}

idi page spinner kosam design chesamu aslau ee page spinner dheikosam use chestamu ante ancor tag daggara redirectayinappdu lanti page kosam ee page loaderniuse chestamu 