from uuid import uuid4 as u4

from core.conf.settings import MYE, ce, prod_mode

class ClassBase:
    def get_id(self, hex=False, long=None):
        id = ""
        if hex:
            if long:
                id = str(u4().hex)[:long]
            else:
                id = str(u4().hex)
        else:
            if long:
                id = str(u4())[:long]
            else:
                id = str(u4())
        return id

    def send_me_error(self, msg):
        if hasattr(self, 'ce'):
            ce_temp = self.ce
        else:
            ce_temp = ce
        error = Exception(msg)
        ce_temp.show_error(error, send_email=False)
    
