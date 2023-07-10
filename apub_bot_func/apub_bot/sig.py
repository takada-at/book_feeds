from httpsig.sign import HeaderSigner
from httpsig.verify import Verifier
from httpsig.utils import generate_message, CaseInsensitiveDict, parse_signature_header


class InjectionableSigner(HeaderSigner):
    def __init__(self, key_id, secret, algorithm=None, headers=None, sign_header='authorization',
                 sign_func = None):
        super(InjectionableSigner, self).__init__(key_id, secret, algorithm, headers, sign_header)
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


class HeaderVerifier(Verifier):
    """
    Verifies an HTTP signature from given headers.
    """

    def __init__(self, headers, secret, required_headers=None, method=None,
                 path=None, host=None, sign_header='authorization'):
        """
        Instantiate a HeaderVerifier object.

        :param headers:             A dictionary of headers from the HTTP
            request.
        :param secret:              The HMAC secret or RSA *public* key.
        :param required_headers:    Optional. A list of headers required to
            be present to validate, even if the signature is otherwise valid.
            Defaults to ['date'].
        :param method:              Optional. The HTTP method used in the
            request (eg. "GET"). Required for the '(request-target)' header.
        :param path:                Optional. The HTTP path requested,
            exactly as sent (including query arguments and fragments).
            Required for the '(request-target)' header.
        :param host:                Optional. The value to use for the Host
            header, if not supplied in :param:headers.
        :param sign_header:         Optional. The header where the signature is.
            Default is 'authorization'.
        """
        required_headers = required_headers or ['date']
        self.headers = CaseInsensitiveDict(headers)

        if sign_header.lower() == 'authorization':
            auth = parse_authorization_header(self.headers['authorization'])
            if len(auth) == 2:
                self.auth_dict = auth[1]
            else:
                raise HttpSigException("Invalid authorization header.")
        else:
            self.auth_dict = parse_signature_header(self.headers[sign_header])

        self.required_headers = [s.lower() for s in required_headers]
        self.method = method
        self.path = path
        self.host = host

        super(HeaderVerifier, self).__init__(
                secret, algorithm=self.auth_dict['algorithm'])

    def verify(self):
        """
        Verify the headers based on the arguments passed at creation and
            current properties.

        Raises an Exception if a required header (:param:required_headers) is
            not found in the signature.
        Returns True or False.
        """
        auth_headers = self.auth_dict.get('headers', 'date').split(' ')

        if len(set(self.required_headers) - set(auth_headers)) > 0:
            error_headers = ', '.join(
                    set(self.required_headers) - set(auth_headers))
            raise Exception(
                    '{} is a required header(s)'.format(error_headers))

        signing_str = generate_message(
                auth_headers, self.headers, self.host, self.method, self.path)
        print("signing_str", signing_str)
        return self._verify(signing_str, self.auth_dict['signature'])