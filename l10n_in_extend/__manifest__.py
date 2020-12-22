# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Indian - Accounting custom',
    'version': '1.0',
    'description': """
Extended Indian Accounting
==========================

Module that computes and stores tax amounts for each invoice lines.
""",
    'category': 'Localization',
    'depends': [
        'l10n_in',
    ],
    'data': [
        'data/account_data.xml',
        'data/account_tax_template_data.xml',
        'data/res_country_state_data.xml',
        'views/account_invoice_views.xml',
        # 'views/report_invoice.xml',
        'views/journal_views.xml',
    ],
}
