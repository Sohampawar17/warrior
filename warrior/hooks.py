app_name = "warrior"
app_title = "Warrior"
app_publisher = "Abhishek Dubey"
app_description = "."
app_email = "Abhishekdubey6674@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "warrior",
# 		"logo": "/assets/warrior/logo.png",
# 		"title": "Warrior",
# 		"route": "/warrior",
# 		"has_permission": "warrior.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/warrior/css/warrior.css"
# app_include_js = "/assets/warrior/js/warrior.js"
app_include_js = "/assets/warrior/js/report_menu_restrict.js"

# include js, css files in header of web template
# web_include_css = "/assets/warrior/css/warrior.css"
# web_include_js = "/assets/warrior/js/warrior.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "warrior/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}
doctype_js = {
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Material Request": "public/js/material_requests.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Sales Order": "public/js/sales_order.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Address": "public/js/address.js",
    "Supplier":"public/js/supplier.js",
     "Payment Entry": "public/js/payment_entry.js",
    "Sales Person":"public/js/sales_person.js"
}
# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "warrior/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "warrior.utils.jinja_methods",
# 	"filters": "warrior.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "warrior.install.before_install"
# after_install = "warrior.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "warrior.uninstall.before_uninstall"
# after_uninstall = "warrior.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "warrior.utils.before_app_install"
# after_app_install = "warrior.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "warrior.utils.before_app_uninstall"
# after_app_uninstall = "warrior.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "warrior.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }
override_doctype_class = {
	"User": "warrior.overrides.user.CustomUser",
}
# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"warrior.tasks.all"
# 	],
# 	"daily": [
# 		"warrior.tasks.daily"
# 	],
# 	"hourly": [
# 		"warrior.tasks.hourly"
# 	],
# 	"weekly": [
# 		"warrior.tasks.weekly"
# 	],
# 	"monthly": [
# 		"warrior.tasks.monthly"
# 	],
# }
scheduler_events = {
    "daily": [
        "warrior.public.payment_entry_hooks.create_draft_pe_for_due_pi_terms",
        "warrior.public.sales_order.cron_update_sales_order_dispatch_status"
    ],
    "cron": {
        "0 19 * * *": [
            "warrior.warrior.doctype.campaign_setting.campaign_setting.import_leads_from_google_sheet"
        ],
         "*/15 * * * *": [
            "warrior.public.sales_invoice_hooks.cron_cancel_cross_warehouse_sre"
        ],
        "*/10 * * * *": [
            "warrior.warrior.doctype.campaign_setting.campaign_setting.auto_assign_campaign_leads"
        ],
         "0 * * * *": [  # Every hour, at minute 0
            "warrior.apis.sales_order.run_full_sync"
        ]
    }
}


# Testing
# -------

# before_tests = "warrior.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "warrior.event.get_events"
# }
override_whitelisted_methods = {
	"erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice": "warrior.public.sales_invoice_hooks.make_sales_invoice_from_sales_order"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "warrior.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["warrior.utils.before_request"]
# after_request = ["warrior.utils.after_request"]

# Job Events
# ----------
# before_job = ["warrior.utils.before_job"]
# after_job = ["warrior.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"warrior.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# apps/warrior/warrior/hooks.py

doc_events = {
     "Lead": {
        "after_insert": "warrior.public.lead.campaign_registration"
    },
      "File": {
        "after_insert": "warrior.public.file.make_images_public"
    },
   "Purchase Order": {
       "before_save":"warrior.public.purchase_order_hooks.fetch_notation",
        "on_submit": "warrior.public.payment_entry_hooks.create_payment_entry_for_po_submit",
        "on_update_after_submit": ["warrior.public.purchase_order_hooks.before_workflow_action","warrior.public.payment_entry_hooks.create_payment_entry_for_po_workflow",
                                "warrior.public.purchase_order_hooks.validate_transporter"],
    },
   "Sales Person": {
        "before_save": "warrior.public.sales_person.before_save",
        "on_trash": "warrior.public.sales_person.on_trash"
    },
     # ✅ Sales Order → Auto Material Request
    "Sales Order": {
         "validate":"warrior.public.sales_order.get_shop_name",
        "on_submit": [
            # "warrior.public.sales_order.create_material_request_from_so",
            "warrior.public.sales_order.set_dispatch_status",
        ],
        "on_update_after_submit": "warrior.public.sales_order.set_dispatch_status_after_submit",
    },
    "Quality Inspection":{
        "on_submit": "warrior.public.quanlity_inspection.set_qty_in_invoice"
    },
    "Purchase Invoice": {
            "before_save": [
                "warrior.public.purchase_order_hooks.fetch_notation",
                "warrior.public.purchase_invoice_hooks.create_format",
                "warrior.public.payment_entry_hooks.make_po_inwarded"
            ],
            "after_save": "warrior.public.payment_entry_hooks.inwared_timestamp_user",
        # "before_submit": "warrior.public.purchase_invoice_hooks.apply_serial_series_before_submit",
        "on_submit": [
        "warrior.public.payment_entry_hooks.create_payment_entry_for_pi_submit",
        "warrior.public.stock_ledger_entry_hooks.update_dispatch_from_purchase_invoice"
    ],
    "on_cancel": [
        "warrior.public.payment_entry_hooks.on_cancel_purchase_invoice",
        "warrior.public.stock_ledger_entry_hooks.update_dispatch_from_purchase_invoice"
    ],
    },
    "Payment Entry": {
        "validate": "warrior.public.payment_entry_hooks.set_order_reference_for_payment_entry",
        "on_submit": "warrior.public.payment_entry_hooks.on_submit",
        "on_cancel": "warrior.public.payment_entry_hooks.on_cancel"
    },
    "Sales Invoice": {
        "validate": ["warrior.public.sales_invoice_hooks.set_transporter_from_sales_order",
                    "warrior.public.sales_invoice_hooks.set_sales_order_from_sales_invoice",
                    "warrior.public.sales_order.get_shop_name",
                    "warrior.public.sales_invoice_hooks.validate_sales_invoice_workflow_transition",
                    # "warrior.public.sales_invoice_hooks.apply_proportional_coupon_discount",
                    "warrior.public.sales_invoice_hooks.validate_return_against_paid_amount",
                    "warrior.public.sales_invoice_hooks.check_customer_closing_balance"
                   ],
        # "before_save":["warrior.public.sales_invoice_hooks.check_customer_closing_balance"],
        "on_submit": ["warrior.public.sales_invoice_hooks.set_dispatch_status_on_submit",
                      "warrior.public.sales_invoice_hooks.set_refunded_item_status",
                    "warrior.public.sales_invoice_hooks.sales_invoice_on_submit",
                      "warrior.public.sales_invoice_hooks.attach_sales_invoice"],
        "on_cancel": ["warrior.public.sales_invoice_hooks.cancel_related_docs_on_cancel",
                       "warrior.public.sales_invoice_hooks.set_refunded_item_status"],
    },
    "Delivery Note": {
        "on_submit": "warrior.public.sales_order.update_dispatch_status_from_delivery_note",
        "on_cancel": "warrior.public.sales_order.update_dispatch_status_from_delivery_note",
    },
    "Serial and Batch Bundle": {
        "before_save": "warrior.public.serial_and_batch_bundle.set_bundle_entry_barcodes"
    },
    "Stock Entry": {
                "validate": "warrior.public.stock_entry_hooks.set_dealer_selling_rate_for_stock_transfer",

        "on_submit": "warrior.public.stock_entry_hooks.update_dispatch_status_from_stock_entry",
        "on_cancel": "warrior.public.stock_entry_hooks.update_dispatch_status_from_stock_entry_cancel",
    },
    # "Stock Ledger Entry": {
    #     "after_submit": "warrior.public.stock_ledger_entry_hooks.update_dispatch_status_from_sle",
    #     "on_cancel": "warrior.public.stock_ledger_entry_hooks.update_dispatch_status_from_sle",
    # },
    "Shipment": {
        "on_submit": "warrior.public.sales_invoice_hooks.set_delivered_from_shipment",
        "on_cancel": "warrior.public.sales_invoice_hooks.update_sales_orders_from_shipment",
    },
"Employee": {
    "autoname": "warrior.public.employee.set_employee_autoname",
        "after_insert": ["warrior.public.employee.ensure_sales_person"],
        "on_update": "warrior.public.employee.ensure_sales_person",
    },
 "Salary Slip": {
        "before_save": "warrior.public.salary_slip_hooks.calculations",
        "after_save": "warrior.public.salary_slip_hooks.after_save_salary_slip"

    },
  "Supplier": {
        "after_insert": "warrior.public.supplier.create_or_update_pricelist",
        "on_update": "warrior.public.supplier.create_or_update_pricelist"
    },
  "User":{
     "before_save": "warrior.public.user.remove_disabled_user_from_campaign"
     },
 "Journal Entry": {
        "on_submit": "warrior.public.journal_entry.update_order_status",
},
  "e-Waybill Log": {
        "before_print": "warrior.public.ewaybill_print.fix_ewaybill_place_names_before_print",
}}

fixtures = [
    {"doctype": "Custom Field", "filters": [["module", "=", "Warrior"]]},
    {"doctype": "Property Setter", "filters": [["module", "=", "Warrior"]]},
    {"doctype": "Client Script", "filters": [["module", "=", "Warrior"]]},
    {"doctype": "Server Script", "filters": [["module", "=", "Warrior"]]},
    # {"doctype": "Workflow", "filters": [["module", "=", "Warrior"]]},
    {"doctype": "Print Format", "filters": [["module", "=", "Warrior"]]},
    {"doctype": "Workspace", "filters": [["module", "=", "Warrior"]]},
]