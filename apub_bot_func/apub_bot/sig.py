from httpsig.sign import HeaderSigner
from httpsig.utils import generate_message, CaseInsensitiveDict


class InjectableSigner(HeaderSigner):
    def __init__(self, key_id, secret, algorithm=None, headers=None, sign_header='authorization',
                 sign_func = None):
        super(InjectableSigner, self).__init__(key_id, secret, algorithm, headers, sign_header)
        self.sign_func = sign_func

    def sign(self, headers, host=None, method=None, path=None):
        """
        Add Signature Authorization header to case-insensitive header dict.

        `headers` is a case-insensitive dict of mutable headers.
        `host` is a override for the 'host' header (defaults to value in
            headers).
        `method` is the HTTP method (required when using '(request-target)').
        `path` is the HTTP path (required when using '(request-target)').
        """
        headers = CaseInsensitiveDict(headers)
        required_headers = self.headers or ['date']
        signable = generate_message(
                    required_headers, headers, host, method, path)
        print(signable)
        if self.sign_func is not None:
            signature = self.sign_func(signable)
        else:
            signature = super(HeaderSigner, self).sign(signable)
        headers[self.sign_header] = self.signature_template % signature

        return headers
