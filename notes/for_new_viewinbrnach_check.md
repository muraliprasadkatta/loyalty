Ee new Django view branch/staff side ki related. Existing staff deactivate/session-kill logic ki compatible ga modify cheyyali.

Check and add required logic:
1. Branch dashboard/page view ayithe @require_branch_session add cheyyi.
2. POST/action view ayithe @require_POST + @require_branch_session add cheyyi.
3. Staff generated QR/PIN/token/access record create chesthe request.session nunchi:
   staff_name = request.session.get("branch_staff_name") or ""
   staff_code = request.session.get("branch_staff_code") or ""
   save cheyyi.
   Reason: staff deactivate/delete ayithe pending QR/PIN/access tokens expire cheyyadaniki staff_code needed.
4. Staff deactivate/delete related view ayithe:
   _kill_staff_active_session(staff)
   _expire_staff_pending_access(branch, staff)
   call cheyyi before delete/deactivate completion.
5. Staff login/OTP flow ayithe inactive staff block cheyyi:
   if staff_obj and not staff_obj.is_active: return 403.
6. Prathi GET/live request ki extra is_active DB check add cheyyaku unless it creates/uses a token or does critical action.
7. Existing branch owner flow break avvakudadhu; branch_staff_id unte matrame staff-specific logic apply cheyyi.