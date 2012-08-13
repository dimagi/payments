var PaymentStatusManager = function (o) {
    var self = this;
    self.updateStatusUrlRoot = o.updateStatusUrlRoot || '/hq/billing/bill/status/';
    self.modal = o.modal || $('#changePaymentStatusModal');
    self.text = {
        yes: "Paid",
        no: "Not Paid"
    };
    self.submit_text = {
        yes: "Mark as Paid",
        no: "Mark as Not Paid"
    };
    self.button_classes = {
        yes: "btn-success paid",
        no: "btn-danger"
    };
    self.label_classes = {
        yes: "label-success",
        no: "label-important"
    };
    self.new_status = 'yes';
    self.bill_id = '';

    self.updateModalForm = function (bill_id) {
        self.bill_id = bill_id;
        var button = $('#update-'+bill_id);
        var domain = button.data('domain'),
            status = (button.hasClass('paid')) ? 'yes' : 'no',
            billing_start = button.data('billingstart'),
            billing_end = button.data('billingend');

        self.new_status = (button.hasClass('paid')) ? 'no' : 'yes';

        self.modal.find('span.domain-name').text(domain);
        self.modal.find('span.billing-start').text(billing_start);
        self.modal.find('span.billing-end').text(billing_end);

        var status_label = self.modal.find('span.label.status');
        status_label.text(self.text[self.new_status]);
        status_label.addClass(self.label_classes[self.new_status]).removeClass(self.label_classes[status]);

        var submit_button = self.modal.find('button[type="submit"]');
        submit_button.text(self.submit_text[self.new_status]);
        submit_button.addClass(self.button_classes[self.new_status]).removeClass(self.button_classes[status]);

        self.modal.find('form').submit(function() {
            self.modal.find('form').ajaxSubmit({
                dataType: 'json',
                url: self.updateStatusUrlRoot+self.bill_id+'/'+self.new_status+'/',
                success: function (data) {
                    if (data.success) {
                        var ref_button = $('#update-'+data.bill_id);
                        ref_button.text(self.text[data.status]);
                        var old_status = (data.status === 'yes') ? 'no' : 'yes';
                        ref_button.removeClass(self.button_classes[old_status]).addClass(self.button_classes[data.status]);

                        self.modal.modal('hide');
                    }
                }
            });
            return false;
        });

    };
};