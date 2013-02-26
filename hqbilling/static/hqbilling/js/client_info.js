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
            url: self.updateClientInfoUrl+self.domain+'/',
            dataType: 'json',
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
            // for some reason ajaxSumit does not parse the html in the JSON correctly?
            // This is a HACK HACK HACK  after some frustration : (
            $.getJSON(self.updateClientInfoUrl+data.domain+'/', function (data) {
                $(".update-client-info-"+data.domain).parent().html(data.button);
            });
            self.modal.modal('hide');

        }
    };
};
