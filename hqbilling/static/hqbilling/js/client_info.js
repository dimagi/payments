var ClientInfoManager = function (o) {
    'use strict';
    var self = this;
    self.updateClientInfoUrl = o.updateClientInfoUrl || '/hq/billing/update_client/';
    self.modal = o.modal || $('#updateClientInfoModal');

    self.updateModalForm = function (domain_name) {
        self.domain = domain_name;
        self.modal.find('.modal-header h3 small').text(self.domain);

        self.grabFormInfo();

        self.modal.find('form').submit(function () {
            $(this).ajaxSubmit({
                type: 'POST',
                dataType: 'json',
                url: self.updateClientInfoUrl+self.domain+'/',
                success: self.updateForm,
                error: function () {}
            });
            return false;
        });

    };

    self.grabFormInfo = function () {
        self.modal.find('.modal-body').text('Loading form...');
        $.ajax({
            dataType: 'json',
            url: self.updateClientInfoUrl+self.domain+'/',
            success: self.updateForm,
            error: function () {
                self.modal.find('.modal-body').text('Sorry, there was an error loading the form. ' +
                    'Try clicking Update again or contact a dev.');
            }
        });
    };

    self.updateForm = function (data) {
        self.modal.find('.modal-body').html(data.form);
        if (data.success) {
            self.modal.modal('hide');
            $(".update-client-info-"+self.domain).parent().html(data.button);
        }
    };
};
