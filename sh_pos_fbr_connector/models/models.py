# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies.
from odoo import fields,models,api,_
import requests
import json
import datetime
import traceback


class Product(models.Model):
    _inherit = 'product.template'

    pct_code = fields.Char("PCT Code", required=False)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_id = fields.Char("POSID")
    fbr_authorization = fields.Char("FBR Header Authorization")
    enable_fbr = fields.Boolean("Enable FBR ?")


class POSOrder(models.Model):
    _inherit = 'pos.order'
    
    fbr_respone = fields.Text("FBR Response")
    post_data_fbr = fields.Boolean("Post Data Successful ?")
    pos_reference = fields.Char(string='Receipt Ref', readonly=True, copy=True)
    invoice_number = fields.Char("Invoice Number")
    return_data_fbr = fields.Boolean(string='Return Data Successful ?')
    return_invoice_number = fields.Char(string='Return Invoice')
    
    def post_data_fbi(self, pos_order_data):
        print('possss', pos_order_data)
        fbr_url = "https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData"
        header = {"Content-Type": "multipart/form-data"}
        invoice_number = ''
        if pos_order_data:
            try:
                for pos_order in pos_order_data:
                    if pos_order.get('is_return_order') == False:
                        order_dic = {
                            "InvoiceNumber": "",
                            "USIN": pos_order.get('name').partition(' ')[2],#"USIN0",
                            "DateTime": pos_order.get('creation_date'),
                            "TotalBillAmount": round(pos_order.get('amount_total'), 4),
                            "TotalSaleValue": round(pos_order.get('amount_total') - pos_order.get('amount_tax'), 4),
                            "TotalTaxCharged": round(pos_order.get('amount_tax'), 4),
                            "PaymentMode": 1,
                            "InvoiceType": 1,
                        }
                        session = self.env['pos.session'].sudo().search([('id','=',pos_order.get('pos_session_id'))])
                        if session:
                            header.update({'Authorization': session.config_id.fbr_authorization})
                            order_dic.update({'POSID': session.config_id.pos_id})
                        partner = False
                        if pos_order.get('partner_id'):
                            partner = self.env['res.partner'].sudo().search([('id', '=', pos_order.get('partner_id'))])
                            order_dic.update({
                                  "BuyerName": partner.name,
                                  "BuyerPhoneNumber": partner.mobile,
                                })
                        if pos_order.get('lines'):
                            items_list = []
                            total_qty = 0.0
                            for line in pos_order.get('lines'):
                                product_dic = line[2]
                                total_qty += product_dic.get('qty')
                                if 'product_id' in product_dic:
                                    product = self.env['product.product'].sudo().search([
                                        ('id', '=', product_dic.get('product_id'))])
                                    if product:
                                        fpos = False
                                        if pos_order.get('fiscal_position_id'):
                                            fpos = pos_order.get('fiscal_position_id')
                                            fpos = self.env['account.fiscal.position'].sudo().browse\
                                                (pos_order.get('fiscal_position_id'))
                                        tax_list = product_dic.get('tax_ids')[0][2]
                                        tax_ids = self.env['account.tax'].sudo().search([('id','in',tax_list)])
                                        pricelist_id = pos_order.get('pricelist_id')
                                        pricelist = self.env['product.pricelist'].sudo().browse(pricelist_id)
                                        tax_ids_after_fiscal_position = fpos.map_tax(tax_ids, product, partner) if fpos else tax_ids
                                        price = float(product_dic.get('price_unit')) * (1 - (product_dic.get('discount') or 0.0) / 100.0)
                                        taxes = tax_ids_after_fiscal_position.compute_all(price, pricelist.currency_id, product_dic.get('qty'), product=product, partner=partner)
                                        line_dic = {
                                            "ItemCode": product.default_code,
                                            "ItemName": product.name,
                                            "Quantity": product_dic.get('qty'),
                                            "PCTCode": product.pct_code,
                                            "TaxRate": tax_ids.amount,
                                            "SaleValue": round(taxes['total_included'] - (taxes['total_included'] - taxes['total_excluded']), 4),
                                            "TotalAmount": round(taxes['total_included'], 4),
                                            "TaxCharged": round(taxes['total_included'] - taxes['total_excluded'], 4),
                                            "InvoiceType": 1,
                                            "RefUSIN": ""
                                        }
                                        items_list.append(line_dic)
                            order_dic.update({'Items': items_list, 'TotalQuantity': total_qty})
                        files = []
                        headers = {}
                        payload = {'api_key': session.config_id.fbr_authorization, 'api_data': json.dumps(order_dic)}
                        payment_response = requests.request("POST", fbr_url, headers=headers, data=payload, files=files)
                        r_json = payment_response.json()
                        res = r_json.get('res')
                        invoice_number = res.get('invoice_no')
            except Exception as e:
                values = dict(
                            exception=e,
                            traceback=traceback.format_exc(),
                        )
        return [invoice_number]

    def post_data_to_fbr_cron(self):
        for failed_orders in self.search([('post_data_fbr','=',False)]):
            failed_orders.post_data_to_fbr_action()
    
    def post_data_to_fbr_action(self):
        orders = []
        for order in self.filtered(lambda x: not x.post_data_fbr):
            orders.append(order.id)
            self.post_data_to_fbr(orders)
    
    def post_data_to_fbr(self, orders):
        fbr_url = "https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData"
        header = {"Content-Type": "multipart/form-data"}
        for order in orders:
            order = self.browse(order)
            try:
                if order and order.session_id and order.session_id.config_id and order.session_id.config_id.fbr_authorization:
                    header.update({'Authorization': order.session_id.config_id.fbr_authorization})
                    bill_amount = order.amount_total
                    tax_amount = order.amount_tax
                    sale_amount = order.amount_total - order.amount_tax
                    order_dic = {
                        "InvoiceNumber": "",
                        "POSID": order.session_id.config_id.pos_id,
                        "USIN": order.pos_reference.partition(' ')[2],
                        "DateTime": datetime.datetime.strptime(order.date_order,"%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S"),
                        "TotalBillAmount": round(bill_amount, 4),
                        "TotalSaleValue": round(sale_amount, 4),
                        "TotalTaxCharged": round(tax_amount, 4),
                        "PaymentMode": 1,
                        "InvoiceType": 1
                    }
                    if order.partner_id:
                        order_dic.update({
                            "BuyerName": order.partner_id.name,
                            "BuyerPhoneNumber": order.partner_id.mobile,
                        })
                    if order.lines:
                        items_list = []
                        total_qty = 0.0
                        for line in order.lines:
                            total_qty += line.qty
                            line_dic = {
                                    "ItemCode": line.product_id.default_code,
                                    "ItemName": line.product_id.name,
                                    "Quantity": line.qty,
                                    "PCTCode": line.product_id.pct_code,
                                    "TaxRate": line.tax_ids_after_fiscal_position.amount,
                                    "SaleValue": line.price_unit,
                                    "TotalAmount": round(line.price_subtotal, 4),
                                    "TaxCharged": round(line.price_subtotal_incl - line.price_subtotal, 4),
                                    "InvoiceType": 1,
                                    "RefUSIN": ""
                                }
                            items_list.append(line_dic)
                        order_dic.update({
                            "Items": items_list,
                            "TotalQuantity":total_qty
                        })
                    payload = {'api_key': order.session_id.config_id.fbr_authorization, 'api_data': json.dumps(order_dic)}
                    files = []
                    headers = {}
                    payment_response = requests.request("POST", fbr_url, headers=headers, data=payload, files=files)
                    print('payment_response', payment_response)
                    print('data', payload)
                    r_json = payment_response.json()
                    res = r_json.get('res')
#                     invoice_number = r_json.get('InvoiceNumber')
                    invoice_number = res.get('invoice_no')
#                     r_json=payment_response.json()
                    order.write({'fbr_respone': r_json, 'post_data_fbr': True, 'invoice_number': invoice_number})
                    
            except Exception as e:
                values = dict(
                            exception=e,
                            traceback=traceback.format_exc(),
                        )
                order.write({'fbr_respone':values})

    def refund(self):
        res = super(POSOrder, self).refund()
        orders = []
        for order in self.filtered(lambda x: not x.return_data_fbr):
            orders.append(order.id)
            self.return_data_from_fbr(orders)
        return res

    def return_data_fbi(self, pos_order_data):
        fbr_url = "https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData"
        header = {"Content-Type": "multipart/form-data"}
        invoice_number = ''
        if pos_order_data:
            try:
                order_dic = {
                    "InvoiceNumber": "",
                    "USIN": pos_order_data.get('name'),
                    "DateTime": pos_order_data.get('creation_date'),
                    "TotalBillAmount": abs(pos_order_data.get('amount_total')),
                    "TotalSaleValue": abs(pos_order_data.get('amount_total') - pos_order_data.get('amount_tax')),
                    "TotalTaxCharged": pos_order_data.get('amount_tax'),
                    "PaymentMode": 1,
                    "InvoiceType": 1,
                }
                session = self.env['pos.session'].sudo().search([('id', '=', pos_order_data.get('pos_session_id'))])
                if session:
                    header.update({'Authorization': session.config_id.fbr_authorization})
                    order_dic.update({'POSID': session.config_id.pos_id})
                partner = False
                if pos_order_data.get('partner_id'):
                    partner = self.env['res.partner'].sudo().search([('id', '=', pos_order_data.get('partner_id'))])
                    order_dic.update({
                        "BuyerName": partner.name,
                        "BuyerPhoneNumber": partner.mobile,
                    })
                if pos_order_data.get('lines'):
                    items_list = []
                    total_qty = 0.0
                    for line in pos_order_data.get('lines'):
                        product_dic = line[2]
                        total_qty += product_dic.get('qty')
                        if 'product_id' in product_dic:
                            product = self.env['product.product'].sudo().search([
                                ('id', '=', product_dic.get('product_id'))])
                            if product:
                                fpos = False
                                if pos_order_data.get('fiscal_position_id'):
                                    fpos = pos_order_data.get('fiscal_position_id')
                                    fpos = self.env['account.fiscal.position'].sudo().browse \
                                        (pos_order_data.get('fiscal_position_id'))
                                tax_list = product_dic.get('tax_ids')[0][2]
                                tax_ids = self.env['account.tax'].sudo().search([('id', 'in', tax_list)])
                                pricelist_id = pos_order_data.get('pricelist_id')
                                pricelist = self.env['product.pricelist'].sudo().browse(pricelist_id)
                                tax_ids_after_fiscal_position = fpos.map_tax(tax_ids, product,
                                                                             partner) if fpos else tax_ids
                                price = float(product_dic.get('price_unit')) * (
                                            1 - (product_dic.get('discount') or 0.0) / 100.0)
                                taxes = tax_ids_after_fiscal_position.compute_all(price, pricelist.currency_id,
                                                                                  product_dic.get('qty'),
                                                                                  product=product, partner=partner)
                                line_dic = {
                                    "ItemCode": product.default_code,
                                    "ItemName": product.name,
                                    "Quantity": abs(product_dic.get('qty')),
                                    "PCTCode": product.pct_code,
                                    "TaxRate": tax_ids.amount,
                                    "SaleValue": product_dic.get('price_unit'),
                                    "TotalAmount": abs(taxes['total_included']),
                                    "TaxCharged": abs(taxes['total_included'] - taxes['total_excluded']),
                                    "InvoiceType": 1,
                                    "RefUSIN": ""
                                }
                                items_list.append(line_dic)
                    order_dic.update({'Items': items_list, 'TotalQuantity': abs(total_qty)})
                files = []
                headers = {}
                payload = {'api_key': session.config_id.fbr_authorization, 'api_data': json.dumps(order_dic)}
                payment_response = requests.request("POST", fbr_url, headers=headers, data=payload, files=files)
                r_json = payment_response.json()
                pos_order = self.env['pos.order'].search([('pos_reference', '=', pos_order_data.get('return_ref'))])
                res = r_json.get('res')
                invoice_number = res.get('invoice_no')
                pos_order.write({'return_data_fbr': True, 'return_invoice_number': invoice_number})
            except Exception as e:
                values = dict(
                    exception=e,
                    traceback=traceback.format_exc(),
                )

            return [invoice_number]

    def return_data_from_fbr(self, orders):
        fbr_url = "https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData"
        header = {"Content-Type": "multipart/form-data"}
        for order in orders:
            order = self.browse(order)
            try:
                if order and order.session_id and order.session_id.config_id and order.session_id.config_id.fbr_authorization:
                    header.update({'Authorization': order.session_id.config_id.fbr_authorization})
                    bill_amount = order.amount_total
                    tax_amount = order.amount_tax
                    sale_amount = order.amount_total - order.amount_tax
                    order_dic = {
                        "InvoiceNumber": "",
                        "POSID": order.session_id.config_id.pos_id,
                        "USIN": order.pos_reference.partition(' ')[2],
                        "DateTime": datetime.datetime.strptime(order.date_order, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S"),
                        "TotalBillAmount": bill_amount,
                        "TotalSaleValue": sale_amount,
                        "TotalTaxCharged": tax_amount,
                        "PaymentMode": 1,
                        "InvoiceType": 1
                    }
                    if order.partner_id:
                        order_dic.update({
                            "BuyerName": order.partner_id.name,
                            "BuyerPhoneNumber": order.partner_id.mobile,
                        })
                    if order.lines:
                        items_list = []
                        total_qty = 0.0
                        for line in order.lines:
                            total_qty += line.qty
                            line_dic = {
                                "ItemCode": line.product_id.default_code,
                                "ItemName": line.product_id.name,
                                "Quantity": line.qty,
                                "PCTCode": line.product_id.pct_code,
                                "TaxRate": line.tax_ids_after_fiscal_position.amount,
                                "SaleValue": line.price_unit,
                                "TotalAmount": line.price_subtotal,
                                "TaxCharged": line.price_subtotal_incl - line.price_subtotal,
                                "InvoiceType": 1,
                                "RefUSIN": ""
                            }
                            items_list.append(line_dic)
                        order_dic.update({
                            "Items": items_list,
                            "TotalQuantity": total_qty
                        })
                    payload = {'api_key': order.session_id.config_id.fbr_authorization, 'api_data': json.dumps(order_dic)}
                    files = []
                    headers = {}
                    payment_response = requests.request("POST", fbr_url, headers=headers, data=payload, files=files)
                    r_json = payment_response.json()
                    res = r_json.get('res')
                    invoice_number = res.get('invoice_no')
                    order.write({'return_data_fbr': True, 'return_invoice_number': invoice_number})
            except Exception as e:
                values = dict(
                    exception=e,
                    traceback=traceback.format_exc(),
                )

    @api.model
    def _order_fields(self, ui_order):
        res = super(POSOrder, self)._order_fields(ui_order)
        res['invoice_number'] = ui_order.get('invoice_number', False)
        res['post_data_fbr'] = ui_order.get('post_data_fbr', False)
        return res

