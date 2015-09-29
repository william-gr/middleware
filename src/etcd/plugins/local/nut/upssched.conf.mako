<%
    ups = dispatcher.call_sync('service.ups.get_config')
%>\
CMDSCRIPT   /usr/local/bin/custom-upssched-cmd
PIPEFN      /var/db/nut/upssched.pipe
LOCKFN      /var/db/nut/upssched.lock

AT NOCOMM   * EXECUTE EMAIL
AT COMMBAD  * START-TIMER COMMBAD 10
AT COMMOK   * CANCEL-TIMER COMMBAD COMMOK
AT FSD      * EXECUTE EMAIL
AT LOWBATT  * EXECUTE EMAIL
AT ONBATT   * START-TIMER ONBATT ${ups['shutdown_timer']}
AT ONBATT   * EXECUTE EMAIL
AT ONLINE   * CANCEL-TIMER ONBATT ONLINE
AT ONLINE   * EXECUTE EMAIL
AT REPLBATT * EXECUTE EMAIL
AT SHUTDOWN * EXECUTE EMAIL
