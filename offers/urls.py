from django.urls import path
from . import admin_views as aviews
from . import user_views  as uviews
from . import branch_views as bviews
from .views_root import root_router   # ← Option B use chesthe: from .view import root_router
from django.urls import include, path
# from . import qr_pin_service 
from .services.qr import qr_pin_service
from offers.services.offer_pin.offer_pin_service import user_generate_offer_pin
from offers.services.offer_pin.offer_pin_verify_service import branch_verify_offer_pin
from offers.services.offer_pin import offer_pin_status_service as opst




app_name = "offers"

urlpatterns = [

    path("", root_router, name="root"),

    path("user/login/",  uviews.user_login_page,  name="user_login"),
    path("auth/otp/send", uviews.otp_send, name="otp_send"),
    path("auth/otp/verify", uviews.otp_verify, name="otp_verify"),  # ← NEW
    path("user/home/",   uviews.user_home_page,  name="user_home"),
    path("logout/", uviews.user_logout_view, name="user_logout"),
    path("user/save-name", uviews.save_display_name, name="save_display_name"),
    path("user/save-location", uviews.save_location, name="save_location"),
    path("offer_progress/<int:branch_id>/",uviews.offer_progress,name="offer_progress"),
    path("qrg/pin-verify/", uviews.pin_verify, name="pin_verify"),
    path("qrg/scan-verify/", uviews.scan_verify, name="scan_verify"),
    path("visit-count/intake/",uviews.user_visit_intake_redirect_view,name="user_visit_intake"),
    path("qrg/confirm-branch-visit/", uviews.confirm_branch_visit, name="confirm_branch_visit"),
    path("visit/pin/", uviews.user_visit_pin_page_view, name="user_visit_pin_page"),
    path("user-status/", uviews.user_status_view, name="user_status"),
    path("visit-pin/verify/",uviews.user_verify_visit_pin,name="user_verify_visit_pin"),
    path("offers/offer-pin/generate/", user_generate_offer_pin, name="user_generate_offer_pin"),
    path("offer-pin/status/<int:offer_pin_id>/", opst.user_offer_pin_status, name="user_offer_pin_status"),
    path("user/branches/",uviews.user_all_branches_view,name="user_all_branches",),



    path("branches/search/", aviews.branches_search, name="branches_search"),
    path("branches/create/", aviews.branches_create, name="branches_create"), 
    path("admin/logout/", aviews.admin_logout_view, name="admin_logout"),
    path("admin/login/", aviews.admin_login_view, name="admin_login"),
    path("admin/home/", aviews.admin_home, name="admin_home"),            # ← /  is home
    path("create/offers/modal/save", aviews.create_offers_modal_save, name="create_offers_modal_save"),
    # path("admin/api/qr/generate/",aviews.api_generate_counter_qr,name="api_generate_counter_qr",),
    path("admin/branch/<int:branch_id>/",aviews.branch_detail_view, name="branch_detail"),
    path("admin/branch/<int:branch_id>/offer-json/", aviews.offer_json_for_branch, name="offer_json_for_branch"),
    path("admin/branch/<int:branch_id>/visit-started-json/", aviews.branch_visit_started_json, name="branch_visit_started_json"),
    path("admin/branch/<int:branch_id>/json/", aviews.branch_json, name="branch_json"),
    path("admin/branch/<int:branch_id>/delete/", aviews.branch_delete, name="branch_delete"),
    path("admin/branches/without-branch-offer/", aviews.branches_without_branch_offer_json, name="branches_without_branch_offer_json"),

    path("qrg/", include(("offers.qr_generation.urls", "qrgen"), namespace="qrgen")),

    path("branch/login/", bviews.branch_login_view, name="branch_login"), 
    path("branch/check",  bviews.branch_check_view, name="branch_check"),  # ← NEW
    path("branch/auth/otp/send", bviews.branch_otp_send, name="branch_otp_send"),
    path("branch/auth/otp/verify", bviews.branch_otp_verify, name="branch_otp_verify"),
    path("branch/home/", bviews.branch_home_view, name="branch_home"),
    path("branch/logout/", bviews.branch_logout_view, name="branch_logout"),
    path("branch/api/users/", bviews.branch_user_visit_list, name="branch_user_visit_list"),
    path("branch/offer-pin/verify/",branch_verify_offer_pin, name="branch_verify_offer_pin"),
    path("branch/visits/",bviews.branch_all_visits, name="branch_all_visits"),
    path("branch/claims/",bviews.branch_all_claims,name="branch_all_claims",),
    path("branch/today-visits/live/",bviews.branch_today_visits_live,name="branch_today_visits_live",),
    path("branch/all-visits/table/live/",bviews.branch_all_visits_table_live,name="branch_all_visits_table_live",),
    path("branch/visits/history/live/",bviews.branch_visit_history_live,name="branch_visit_history_live",),
    path("branch/all-claims/",bviews.branch_all_claims,name="branch_all_claims"),
    path("branch/all-claims/live/",bviews.branch_all_claims_table_live,name="branch_all_claims_table_live",),
    path("branch/staff/",bviews.branch_staff_manage,name="branch_staff_manage",),

    path("branch/staff/send-otp/",bviews.branch_staff_send_otp_view,name="branch_staff_send_otp",),

    path("branch/staff/verify-otp/",bviews.branch_staff_verify_otp_and_create_view,name="branch_staff_verify_otp",),
        # offers/urls.py
    path("branch/staff/<int:staff_id>/delete/",bviews.branch_staff_delete,name="branch_staff_delete",),
    path("branch/staff/<int:staff_id>/reactivate/",bviews.branch_staff_reactivate,name="branch_staff_reactivate",),
    path("branch/visit-pin/generate/",qr_pin_service.branch_generate_visit_pin,name="branch_generate_visit_pin",),

    path("branch/staff/<int:staff_id>/edit/start/",bviews.branch_staff_edit_start_view,name="branch_staff_edit_start",),

    path("branch/staff/<int:staff_id>/edit/verify/",bviews.branch_staff_edit_verify_otp_view,name="branch_staff_edit_verify_otp",),

]
