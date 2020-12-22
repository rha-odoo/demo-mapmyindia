# -*- encoding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Indian - E Invoice",
    "version": "1.0",
    "description": """
E-invoice for India Accounting
==============================

This module connects with ODOO IAP
Government API version is 1.01
    """,
    "category": "Accounting/Accounting",
    "depends": ["l10n_in_extend"],
    "data": [
        "security/ir.model.access.csv",
        "data/account_invoice_json.xml",
        "views/report_invoice.xml",
        "wizard/generate_token_wizard_views.xml",
        "wizard/einvoice_cancel_wizard_views.xml",
        "views/res_config_settings_views.xml",
        "views/account_invoice_views.xml",
    ],
    "license": "OEEL-1",
}
