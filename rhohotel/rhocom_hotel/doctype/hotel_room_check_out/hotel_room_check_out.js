frappe.ui.form.on('Hotel Room Check Out', {
    refresh: function(frm) {
        if (frm.doc.check_in) {
            frappe.call({
                method: 'rhohotel.rhocom_hotel.doctype.hotel_room_check_out.hotel_room_check_out.get_linked_documents',
                args: {
                    check_in: frm.doc.check_in
                },
                callback: function(r) {
                    if (r.message) {
                        frm.get_field('invoices_html').$wrapper.html(render_invoices(r.message.invoices));
                        frm.get_field('payments_html').$wrapper.html(render_payments(r.message.payments));
                        frm.set_value('total_outstanding_amount', r.message.total_outstanding_amount);

                        if (r.message.total_outstanding_amount > 0) {
                            frm.add_custom_button(__('Pay with Moniepoint'), function() {
								var invoice_names = r.message.invoices.map(function(inv) { return inv.name; });
                                frappe.call({
                                    method: 'rhohotel.api.initiate_payment',
                                    args: {
                                        invoice_names: invoice_names
                                    },
                                    callback: function(response) {
                                        if (response.message) {
											frappe.msgprint("Payment session created: " + response.message.name);
											let frm = frappe.get_doc("Payment Session", response.message.name);
											frappe.ui.form.get_req_handler("Payment Session", response.message.name).open_payment_dialog(frm);
                                        } else {
                                            frappe.msgprint(__('Failed to initiate Moniepoint payment.'));
                                        }
                                    }
                                });
                            }, __('Actions'));
                        }
                    }
                }
            });
        }
    }
});

function render_invoices(invoices) {
    let html = `<table class="table table-bordered">
        <thead>
            <tr>
                <th>Sales Invoice</th>
                <th>Customer</th>
                <th>Posting Date</th>
                <th>Grand Total</th>
                <th>Balance</th>
            </tr>
        </thead>
        <tbody>`;
    if (invoices.length > 0) {
        invoices.forEach(invoice => {
            html += `<tr>
                <td><a href="/app/sales-invoice/${invoice.name}">${invoice.name}</a></td>
                <td>${invoice.customer}</td>
                <td>${frappe.datetime.str_to_user(invoice.posting_date)}</td>
                <td>${format_currency(invoice.grand_total)}</td>
                <td>${format_currency(invoice.outstanding_amount)}</td>
            </tr>`;
        });
    } else {
        html += '<tr><td colspan="5" class="text-center">No Invoices Found</td></tr>';
    }
    html += '</tbody></table>';
    return html;
}

function render_payments(payments) {
    let html = `<table class="table table-bordered">
        <thead>
            <tr>
                <th>Payment Entry</th>
                <th>Party</th>
                <th>Posting Date</th>
                <th>Paid Amount</th>
            </tr>
        </thead>
        <tbody>`;
    if (payments.length > 0) {
        payments.forEach(payment => {
            html += `<tr>
                <td><a href="/app/payment-entry/${payment.name}">${payment.name}</a></td>
                <td>${payment.party}</td>
                <td>${frappe.datetime.str_to_user(payment.posting_date)}</td>
                <td>${format_currency(payment.paid_amount)}</td>
            </tr>`;
        });
    } else {
        html += '<tr><td colspan="4" class="text-center">No Payments Found</td></tr>';
    }
    html += '</tbody></table>';
    return html;
}
