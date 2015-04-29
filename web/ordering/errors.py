import collections
from espa_common import settings
from espa_common import sensor
import datetime
import emails


class Errors(object):
    '''Implementation for ESPA errors.resolve(error_message) interface'''

    def __init__(self, name=None):
        self.product_name = name

        #build list of known error conditions to be checked
        self.conditions = list()

        self.conditions.append(self.db_lock_errors)
        self.conditions.append(self.dswe_unavailable)
        self.conditions.append(self.ftp_errors)
        self.conditions.append(self.http_errors)
        self.conditions.append(self.gzip_errors)
        self.conditions.append(self.gzip_errors_online_cache)
        self.conditions.append(self.lta_soap_errors)
        self.conditions.append(self.missing_aux_data)
        self.conditions.append(self.network_errors)
        self.conditions.append(self.night_scene)
        self.conditions.append(self.no_such_file_or_directory)
        self.conditions.append(self.oli_no_sr)
        self.conditions.append(self.only_only_no_thermal)
        self.conditions.append(self.ssh_errors)

        #construct the named tuple for the return value of this module
        self.resolution = collections.namedtuple('ErrorResolution',
                                                 ['status', 'reason', 'extra'])

        #set our internal retry dictionary to the settings.RETRY
        #in the future, retrieve it from a database or elsewhere if necessary
        self.retry = settings.RETRY

    def __find_error(self, error_message, key, status, reason, extra=None):
        '''Logic to search the error_message and return the appropriate value

        Keyword args:
        error_message  - The error_message to be searched
        key - The string to search for in the error_message
        status - The resulting status that should be set if the key is found
        reason - The user facing reason the status was returned
        extra - A dictionary with extra parameters, such as retry_after if
                the status was 'retry'

        Returns:
        An Errors.ErrorResolution() named tuple or None

        ErrorResolution.status - The status a product should be set to
        ErrorResolution.reason - The reason the status was set
        '''
        for key in self.keys:
            if key.lower() in error_message.lower():
                return self.resolution(status, reason, extra)
            else:
                return None

    def __add_retry(self, timeout_key, extras=dict()):
        ''' Adds retry_after to the extras dictionary based on the supplied
        timeout_keyemail_addr

        Keyword args:
        timeout_key - Name of timeout key defined in espa_common.settings.RETRY
        extras - The dictionary to add the retry_after value to

        Returns:
        A dictionary with retry_after populated with the datetimestamp after
        which an operation should be retried.
        '''
        timeout = self.retry[timeout_key]['timeout']
        ts = datetime.datetime.now()
        extras['retry_after'] = ts + datetime.timedelta(seconds=timeout)
        extras['retry_limit'] = self.retry[timeout_key]['retry_limit']
        return extras

    def ssh_errors(self, error_message):
        ''' errors creating directories or transferring statistics '''
        keys = [('Application failed to execute '
                 '[ssh -q -o StrictHostKeyChecking=no'), ]

        status = 'retry'
        reason = 'ssh operations interrupted'
        extras = self.__add_retry('ssh_errors')
        return self.__find_error(error_message, keys, status, reason, extras)

    def http_errors(self, error_message):
        ''' http call errors '''
        keys = ['Read timed out.',
                'Connection aborted.',
                'Connection timed out',
                'Connection broken: IncompleteRead',
                '502 Server Error: Proxy Error',
                '404 Client Error: Not Found']
        status = 'retry'
        reason = 'HTTP connection error'
        extras = self.__add_retry('http_errors')
        return self.__find_error(error_message, keys, status, reason, extras)

    def db_lock_errors(self, error_message):
        ''' there were problems updating the database '''
        keys = ['Lock wait timeout exceeded']
        status = 'retry'
        reason = 'database lock timed out'
        extras = self.__add_retry('db_lock_timeout')
        return self.__find_error(error_message, keys, status, reason, extras)

    def gzip_errors(self, error_message):
        ''' there were problems gzipping products '''
        keys = ['not in gzip format',
                'gzip: stdin: unexpected end of file']
        status = 'retry'
        reason = 'error unpacking gzip'
        extras = self.__add_retry('gzip_errors')

        return self.__find_error(error_message, keys, status, reason, extras)
        
    def gzip_errors_online_cache(self, error_message):
        ''' products on cache are corrupted '''
        keys = ['gzip: stdin: invalid compressed data--format violated']
        status = 'retry'
        reason = 'Input gzip corrupt'
        extras = self.__add_retry('gzip_errors')

        if isinstance(sensor.instance(self.product_name), sensor.Landsat):
            emails.Emails().send_gzip_error_email(self.product_name)
        
        return self.__find_error(error_message, keys, status, reason, extras)

    def oli_no_sr(self, error_message):
        ''' Indicates the user requested sr processing against OLI-only'''

        keys = ['oli-only cannot be corrected to surface reflectance',
                ('include_sr is an unavailable '
                 'product option for OLI-Only data')]
        status = 'unavailable'
        reason = 'OLI only scenes cannot be processed to surface reflectance'
        return self.__find_error(error_message, keys, status, reason)

    def night_scene(self, error_message):
        '''Indicates that LEDAPS/l8sr could not process a scene because the
        sun was beneath the horizon'''

        keys = ['solar zenith angle out of range',
                'Solar zenith angle is out of range']
        status = 'unavailable'
        reason = ('This scene cannot be processed to surface reflectance '
                  'due to the high solar zenith angle')
        return self.__find_error(error_message, keys, status, reason)

    def missing_aux_data(self, error_message):
        '''Could not run do to aux data no available yet'''

        keys = ['Verify the missing auxillary data products',
                'Could not find auxnm data file:']
        status = 'retry'
        reason = 'Auxillary data not yet available for this date'
        extras = self.__add_retry('missing_aux_data')
        return self.__find_error(error_message, keys, status, reason, extras)

    def ftp_errors(self, error_message):
        keys = ['timed out|150 Opening BINARY mode data connection',
                '500 OOPS',
                'ftplib.error_reply']
        status = 'retry'
        reason = 'FTP error'
        extras = self.__add_retry('ftp_errors')
        return self.__find_error(error_message, keys, status, reason, extras)

    def network_errors(self, error_message):
        keys = ['Network is unreachable',
                'Connection timed out']
        status = 'retry'
        reason = 'Network error'
        extras = self.__add_retry('network_errors')
        return self.__find_error(error_message, keys, status, reason, extras)

    def no_such_file_or_directory(self, error_message):
        keys = ['No such file or directory']
        status = 'submitted'
        reason = 'Reordered due to online cache purge'
        return self.__find_error(error_message, keys, status, reason)

    def dswe_unavailable(self, error_message):
        keys = ['include_dswe is an unavailable product option for OLITIRS']
        status = 'unavailable'
        reason = 'DSWE is not available for OLI/TIRS products'
        return self.__find_error(error_message, keys, status, reason)

    def only_only_no_thermal(self, error_message):
        keys = [('include_sr_thermal is an unavailable '
                 'product option for OLI-Only data')]
        status = 'unavailable'
        reason = 'Brightness temperature is not available for OLI-only data'
        return self.__find_error(error_message, keys, status, reason)

    def lta_soap_errors(self, error_message):
        keys = ['Listener refused the connection with the following error']
        status = 'retry'
        reason = 'Could not complete order at this time'
        extras = self.__add_retry('lta_soap_errors')
        return self.__find_error(error_message, keys, status, reason, extras)


def resolve(error_message, name):
    '''Attempts to automatically determine the disposition of a scene given
    the error_message that is supplied.

    Keyword args:
    error_message - The full error message received from the backend processing
                    node.
    name - The name of the product the error occurred on

    Returns:
    A named tuple of espa product status code and user facing message that
    should be displayed, or None if it cannot be determined.

    Note that this method will return only the first resolution it can find,
    with the search order being defined in the Errors().conditions list.

    Example 1:
    #Night scene that contains 'solar zenith out of range' in the error_message
    result = resolve(error_message)
    print(result.status)
    'unavailable'

    print(result.reason)
    'Night scenes cannot be processed to surface reflectance'

    Example 2:
    #Cannot be determined based on the supplied message
    result = resolve(error_message)
    print(result is None)
    True

    Example 3:
    #A condition which should be retried after a configured period
    result = resolve(error_message)
    print(result.status)
    'retry'

    print(result.reason)
    'Auxillary data not yet available for this date'

    print(result.extra)
    {
    'retry_after': datetime.datetime(2014, 10, 29, 9, 48, 59, 758093),
    'retry_limit': 5
    }

    '''

    conditions = None
    result = None
    try:
        conditions = Errors().conditions
        for condition in conditions:
            result = condition(error_message)
            if result is not None:
                return result
        else:
            return None
    finally:
        conditions = None
        result = None
