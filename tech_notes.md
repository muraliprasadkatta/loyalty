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