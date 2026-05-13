import re
from storages.backends.s3boto3 import S3Boto3Storage

class MediaFileStorage(S3Boto3Storage):
    location = 'testing/media'
    file_overwrite = False
    default_acl = None

    def get_available_name(self, name, max_length=None):
        name = re.sub('[\\s]+', '_', name)
        name = re.sub('[()[\\]{}\\"\\\'`]', '_', name)
        name = re.sub('_+', '_', name)
        return super().get_available_name(name, max_length)

    def url(self, name, parameters=None, expire=None, http_method=None):
        url = super().url(name, parameters=parameters, expire=expire, http_method=http_method)
        url = url.strip('\'"')
        return url
