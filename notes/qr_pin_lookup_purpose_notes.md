# `offers/services/qr/qr_pin_lookup.py` — Purpose Notes

## File path

```text
D:\restarent_application66\offers\services\qr\qr_pin_lookup.py
```

## Why this file was created

This file was created to make QR/PIN verification faster, safer, and cleaner.

Before this helper, `/qrg/pin-verify/` logic was depending on a slow pattern:

```python
for row in active_yash_pins:
    if check_password(pin, row.pin_hash):
        # matched
```

That means every PIN verify request had to scan multiple active `YashPin` rows and run `check_password()` repeatedly.

That is costly because password-hash checking is intentionally slow. Under real users or load testing, this can become a bottleneck.

## Main purpose

`qr_pin_lookup.py` creates a deterministic lookup value for a QR PIN.

The important helper is:

```python
make_qr_pin_lookup(pin)
```

Its job is to convert the user-entered PIN into a stable lookup key using an HMAC secret.

So instead of checking many rows one by one, the backend can directly query:

```python
YashPin.objects.filter(pin_lookup=make_qr_pin_lookup(pin), used=False, expires_at__gt=now)
```

That gives a much faster DB-level lookup.

## What problem it solves

### 1. Removes slow Python loops

Old logic:

```python
load many active pins
check_password() each pin
stop when matched
```

New logic:

```python
make lookup key
query exact matching row
```

This is much better for performance.

### 2. Helps PostgreSQL do the work

If `pin_lookup` is stored in DB and indexed, PostgreSQL can find the matching PIN quickly.

That is better than Django/Python manually checking 50, 100, or 120 active rows.

### 3. Keeps the raw PIN hidden

The lookup value is not the raw PIN.

It is generated using HMAC with a secret key like:

```python
OZ_QR_PIN_LOOKUP_SECRET
```

So the DB does not need to store plain PIN values.

### 4. Makes PIN verification cleaner

The PIN lookup logic is separated into its own service file.

So `user_views.py` does not need to know the hashing/lookup details.

This keeps the view cleaner and makes future changes easier.

## Why not use only `check_password()`?

`check_password()` is good for secure verification, but it is not good for finding which row matches when we only have the entered PIN.

Password hashes are salted, so the same PIN can produce different hashes each time.

That means we cannot query like:

```python
YashPin.objects.get(pin_hash=...)
```

So the old code had to check rows one by one.

`pin_lookup` solves the lookup part.

A good pattern is:

1. Use `pin_lookup` to find the candidate row quickly.
2. Optionally still use `check_password(pin, row.pin_hash)` as a final safety check.

## Example flow

### When QR PIN is created

When a `YashPin` is created:

```python
raw_pin = "AK47"

YashPin.objects.create(
    pin_hash=make_password(raw_pin),
    pin_lookup=make_qr_pin_lookup(raw_pin),
    ...
)
```

### When user enters PIN

When user submits PIN:

```python
pin = request.POST["pin"]

lookup = make_qr_pin_lookup(pin)

row = (
    YashPin.objects
    .select_related("qr_token", "qr_token__branch")
    .filter(
        pin_lookup=lookup,
        used=False,
        expires_at__gt=timezone.now(),
    )
    .first()
)
```

Then backend can verify the matched row and continue the QR/PIN visit flow.

## Security reason

The lookup must use HMAC, not a plain hash.

Bad:

```python
sha256(pin)
```

Better:

```python
hmac(secret, normalized_pin)
```

Reason: QR PIN is short. If plain SHA-256 is used, attackers can precompute all possible PINs.

With HMAC, the lookup depends on the secret key, so precomputed public tables are not useful.

## Important design rule

`pin_lookup` is for lookup only.

It should not replace all validation.

After lookup, the flow still needs normal checks:

- PIN is not expired
- PIN is not used
- QR token is not expired
- QR token is not used
- Branch context is correct
- Same user did not already visit the branch today
- Token/PIN is locked transactionally before marking used
- Visit event is created only once

## Branch safety note

There was another risk in the older PIN flow: if PIN lookup is global across all active PINs, the same 4-character PIN could exist in multiple branches at the same time.

So the safer long-term flow is:

```python
pin_lookup + branch/public_id context
```

That avoids accidentally matching a PIN from another branch.

## What this file should contain

This file should stay small and focused.

Good responsibilities:

- Normalize PIN consistently
- Build deterministic HMAC lookup
- Hide raw implementation details from views/services

Example responsibilities:

```python
normalize_qr_pin(pin)
make_qr_pin_lookup(pin)
```

## What this file should NOT do

This file should not:

- Create visits
- Mark QR tokens used
- Mark YashPin used
- Decide offer eligibility
- Issue claims
- Read or write request/session
- Handle redirects
- Contain view logic

Those responsibilities should stay in service/view layers.

## Why this is useful for load testing

During load testing, `/qrg/pin-verify/` can receive many simultaneous requests.

If every request scans 120 active rows and runs `check_password()` repeatedly, CPU usage increases quickly.

With `pin_lookup`, most work becomes:

```text
1 DB indexed lookup + 1 final validation
```

That is much more scalable.

## Simple explanation

`qr_pin_lookup.py` is like a fast search key generator for QR PINs.

It lets Django find the correct active `YashPin` directly instead of checking many PIN hashes one by one.

## Final summary

We created `qr_pin_lookup.py` because PIN verification needed a fast, secure lookup method.

It helps solve:

- slow `/qrg/pin-verify/`
- repeated `check_password()` loops
- poor scalability under load
- messy PIN lookup logic inside `user_views.py`

It does not complete the full verification by itself. It only helps find the correct candidate PIN row quickly and safely.
