var HQBillingRates = function (options) {
    var self = this;
    self.rateItemType = options.rateItemType;
    self.newRateURL = options.newRateURL;
    self.newRateModal = (options.newRateModal) ? $(options.newRateModal) : $('#addRateModal');
    self.newRateForm = self.newRateModal.find('form');

    self.updateRateModal = options.updateRateModal;
    self.updateRateForm = (self.updateRateModal) ? self.updateRateModal.find('form') : null;
    self.currentRateID = "";

    self.init = function () {
        $(function () {
            $.ajax({
                dataType: 'json',
                url: self.newRateURL,
                success: updateNewRateForm

            });

            self.newRateForm.submit(function () {
                console.log(this);
                $(this).find('button[type="submit"]').button('loading');
                $(this).ajaxSubmit({
                    dataType: 'json',
                    url: self.newRateURL,
                    success: updateNewRateForm
                });
                return false;
            });

            if(self.updateRateModal)
                self.updateRateForm.find('.modal-footer button[type="submit"]').click(function () {
                    var delete_param = "";
                    if ($(this).hasClass('btn-danger')) {
                        delete_param = "?delete=true";
                    }

                    self.updateRateForm.ajaxSubmit({
                        dataType: 'json',
                        url: self.newRateURL+self.rateItemType+'/'+self.currentRateID+'/'+delete_param,
                        success: function (data) {
                            var row = $('[data-rateid="'+self.currentRateID+'"]').parent().parent()[0];
                            if (data.deleted)
                                reportTables.datatable.fnDeleteRow(reportTables.datatable.fnGetPosition(row));
                            if (data.success)
                                self.updateRateModal.modal('hide');
                            if (data.success && !data.deleted)
                                updateRow(row, data.rows[0]);
                            self.updateRateModal.find('.modal-body').html(data.form_update);
                        }
                    });
                    return false;
                });
        });

    };

    self.updateRate = function (button) {
        self.currentRateID = $(button).data('rateid');
        $.ajax({
            dataType: 'json',
            url: self.newRateURL+self.rateItemType+'/'+self.currentRateID+'/',
            success: function (data) {
                self.updateRateModal.find('.modal-body').html(data.form_update);
            }
        });
    };

    var updateNewRateForm = function (data) {
            console.log(self.newRateForm);
            self.newRateForm.find('button[type="submit"]').button('reset');
            if (data.success)
                self.newRateModal.modal('hide');
            self.newRateModal.find('.modal-body').html(data.form_update);
        },
        updateRow = function (rowElem, rowData) {
            $('.datatable tbody tr').removeClass('active');
            $.each($(rowElem).children(), function (ind) {
                $(this).html(rowData[ind]);
            });
            $(rowElem).addClass('active');
        };


};