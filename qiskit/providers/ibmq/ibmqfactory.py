
# -*- coding: utf-8 -*-

# This code is part of Qiskit.
#
# (C) Copyright IBM 2017, 2019.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Factory and credentials manager for IBM Q Experience."""

import logging
import warnings
from typing import Dict, List, Union, Optional, Any
from collections import OrderedDict

from .accountprovider import AccountProvider
from .api.clients import AuthClient, VersionClient
from .credentials import Credentials, discover_credentials
from .credentials.configrc import (read_credentials_from_qiskitrc,
                                   remove_credentials,
                                   store_credentials)
from .credentials.updater import update_credentials
from .exceptions import IBMQAccountError, IBMQApiUrlError, IBMQProviderError


logger = logging.getLogger(__name__)

QX_AUTH_URL = 'https://auth.quantum-computing.ibm.com/api'
UPDATE_ACCOUNT_TEXT = (
    'Please update your accounts and programs by following the instructions here:\n'
    'https://github.com/Qiskit/qiskit-ibmq-provider#updating-to-the-new-ibm-q-experience')


class IBMQFactory:
    """Factory and credentials manager for IBM Q Experience."""

    def __init__(self) -> None:
        self._credentials = None  # type: Optional[Credentials]
        self._providers = OrderedDict()

    # Account management functions.

    def enable_account(
            self,
            token: str,
            url: str = QX_AUTH_URL,
            **kwargs: Any
    ) -> Optional[AccountProvider]:
        """Authenticate against IBM Q Experience for use during this session.

        Note: with version 0.4 of this qiskit-ibmq-provider package, use of
            the legacy Quantum Experience and Qconsole (also known
            as the IBM Q Experience v1) credentials is fully deprecated.

        Args:
            token (str): IBM Q Experience API token.
            url (str): URL for the IBM Q Experience authentication server.
            **kwargs (dict): additional settings for the connection:
                * proxies (dict): proxy configuration.
                * verify (bool): verify the server's TLS certificate.

        Returns:
            AccountProvider: the provider for the default open access project.

        Raises:
            IBMQAccountError: if an IBM Q Experience account is already in
                use.
            IBMQApiUrlError: if the URL is not a valid IBM Q Experience
                authentication URL.
        """
        # Check if an IBM Q Experience account is already in use.
        if self._credentials:
            raise IBMQAccountError('An IBM Q Experience account is already '
                                   'enabled.')

        # Check the version used by these credentials.
        credentials = Credentials(token, url, **kwargs)
        version_info = self._check_api_version(credentials)

        # Check the URL is a valid authentication URL.
        if not version_info['new_api'] or 'api-auth' not in version_info:
            raise IBMQApiUrlError(
                'The URL specified ({}) is not an IBM Q Experience '
                'authentication URL'.format(credentials.url))

        # Initialize the providers.
        self._initialize_providers(credentials)

        # Prevent edge case where no hubs are available.
        providers = self.providers()
        if not providers:
            warnings.warn('No Hub/Group/Projects could be found for this '
                          'account.')
            return None

        return providers[0]

    def disable_account(self) -> None:
        """Disable the account in the current session.

        Raises:
            IBMQAccountError: if no account is in use in the session.
        """
        if not self._credentials:
            raise IBMQAccountError('No account is in use for this session.')

        self._credentials = None
        self._providers = OrderedDict()

    def load_account(self) -> Optional[AccountProvider]:
        """Authenticate against IBM Q Experience from stored credentials.

        Returns:
            AccountProvider: the provider for the default open access project.

        Raises:
            IBMQAccountError: if no IBM Q Experience credentials can be found.
        """
        # Check for valid credentials.
        credentials_list = list(discover_credentials().values())

        if not credentials_list:
            raise IBMQAccountError(
                'No IBM Q Experience credentials found on disk.')

        if len(credentials_list) > 1:
            raise IBMQAccountError('Multiple IBM Q Experience credentials '
                                   'found. ' + UPDATE_ACCOUNT_TEXT)

        credentials = credentials_list[0]
        # Explicitly check via an API call, to allow environment auth URLs
        # contain API 2 URL (but not auth) slipping through.
        version_info = self._check_api_version(credentials)

        # Check the URL is a valid authentication URL.
        if not version_info['new_api'] or 'api-auth' not in version_info:
            raise IBMQAccountError('Invalid IBM Q Experience credentials '
                                   'found. ' + UPDATE_ACCOUNT_TEXT)

        # Initialize the providers.
        if self._credentials:
            # For convention, emit a warning instead of raising.
            warnings.warn('Credentials are already in use. The existing '
                          'account in the session will be replaced.')
            self.disable_account()

        self._initialize_providers(credentials)

        # Prevent edge case where no hubs are available.
        providers = self.providers()
        if not providers:
            warnings.warn('No Hub/Group/Projects could be found for this '
                          'account.')
            return None

        return providers[0]

    @staticmethod
    def save_account(
            token: str,
            url: str = QX_AUTH_URL,
            overwrite: bool = False,
            **kwargs: Any
    ) -> None:
        """Save the account to disk for future use.

        Args:
            token (str): IBM Q Experience API token.
            url (str): URL for the IBM Q Experience authentication server.
            overwrite (bool): overwrite existing credentials.
            **kwargs (dict):
                * proxies (dict): Proxy configuration for the API.
                * verify (bool): If False, ignores SSL certificates errors

        Raises:
            IBMQApiUrlError: if the URL is not a valid IBM Q Experience
                authentication URL.
        """
        if url != QX_AUTH_URL:
            raise IBMQApiUrlError('Invalid IBM Q Experience credentials '
                                  'found. ' + UPDATE_ACCOUNT_TEXT)

        credentials = Credentials(token, url, **kwargs)

        store_credentials(credentials, overwrite=overwrite)

    @staticmethod
    def delete_account() -> None:
        """Delete the saved account from disk.

        Raises:
            IBMQAccountError: if no valid IBM Q Experience credentials found.
        """
        stored_credentials = read_credentials_from_qiskitrc()
        if not stored_credentials:
            raise IBMQAccountError('No credentials found.')

        if len(stored_credentials) != 1:
            raise IBMQAccountError('Multiple credentials found. ' +
                                   UPDATE_ACCOUNT_TEXT)

        credentials = list(stored_credentials.values())[0]

        if credentials.url != QX_AUTH_URL:
            raise IBMQAccountError('Invalid IBM Q Experience credentials '
                                   'found. ' + UPDATE_ACCOUNT_TEXT)

        remove_credentials(credentials)

    @staticmethod
    def stored_account() -> Dict[str, str]:
        """List the account stored on disk.

        Returns:
            dict: dictionary with information about the account stored on disk.

        Raises:
            IBMQAccountError: if no valid IBM Q Experience credentials found.
        """
        stored_credentials = read_credentials_from_qiskitrc()
        if not stored_credentials:
            return {}

        if (len(stored_credentials) > 1 or
                list(stored_credentials.values())[0].url != QX_AUTH_URL):
            raise IBMQAccountError('Invalid IBM Q Experience credentials '
                                   'found. ' + UPDATE_ACCOUNT_TEXT)

        credentials = list(stored_credentials.values())[0]
        return {
            'token': credentials.token,
            'url': credentials.url
        }

    def active_account(self) -> Optional[Dict[str, str]]:
        """List the IBM Q Experience account currently in the session.

        Returns:
            dict: information about the account currently in the session.
        """
        if not self._credentials:
            # Return None instead of raising, maintaining the same behavior
            # of the classic active_accounts() method.
            return None

        return {
            'token': self._credentials.token,
            'url': self._credentials.url,
        }

    @staticmethod
    def update_account(force: bool = False) -> Optional[Credentials]:
        """Interactive helper from migrating stored credentials to IBM Q Experience v2.

        Args:
            force (bool): if `True`, disable interactive prompts and perform
                the changes.

        Returns:
            Credentials: if the updating is possible, credentials for the API
            version 2; and `None` otherwise.
        """
        return update_credentials(force)

    # Provider management functions.

    def providers(
            self,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None
    ) -> List[AccountProvider]:
        """Return a list of providers with optional filtering.

        Args:
            hub (str): name of the hub.
            group (str): name of the group.
            project (str): name of the project.

        Returns:
            list[AccountProvider]: list of providers that match the specified
                criteria.
        """
        filters = []

        if hub:
            filters.append(lambda hgp: hgp.hub == hub)
        if group:
            filters.append(lambda hgp: hgp.group == group)
        if project:
            filters.append(lambda hgp: hgp.project == project)

        providers = [provider for key, provider in self._providers.items()
                     if all(f(key) for f in filters)]

        return providers

    def get_provider(
            self,
            hub: Optional[str] = None,
            group: Optional[str] = None,
            project: Optional[str] = None
    ) -> AccountProvider:
        """Return a provider for a single hub/group/project combination.

        Returns:
            AccountProvider: provider that match the specified criteria.

        Raises:
            IBMQProviderError: if no provider matches the specified criteria,
                or more than one provider match the specified criteria.
        """
        providers = self.providers(hub, group, project)

        if not providers:
            raise IBMQProviderError('No provider matching the criteria')
        if len(providers) > 1:
            raise IBMQProviderError('More than one provider matching the '
                                    'criteria')

        return providers[0]

    # Private functions.

    @staticmethod
    def _check_api_version(credentials: Credentials) -> Dict[str, Union[bool, str]]:
        """Check the version of the API in a set of credentials.

        Returns:
            dict: dictionary with version information.
        """
        version_finder = VersionClient(credentials.base_url,
                                       **credentials.connection_parameters())
        return version_finder.version()

    def _initialize_providers(self, credentials: Credentials) -> None:
        """Authenticate against IBM Q Experience and populate the providers.

        Args:
            credentials (Credentials): credentials for IBM Q Experience.

        Raises:
            IBMQApiUrlError: if the credentials do not belong to a IBM Q
                Experience authentication URL.
        """
        auth_client = AuthClient(credentials.token,
                                 credentials.base_url,
                                 **credentials.connection_parameters())
        service_urls = auth_client.current_service_urls()
        user_hubs = auth_client.user_hubs()

        self._credentials = credentials
        for hub_info in user_hubs:
            # Build credentials.
            provider_credentials = Credentials(
                credentials.token,
                url=service_urls['http'],
                websockets_url=service_urls['ws'],
                proxies=credentials.proxies,
                verify=credentials.verify,
                **hub_info,)

            # Build the provider.
            try:
                provider = AccountProvider(provider_credentials,
                                           auth_client.current_access_token())
                self._providers[provider_credentials.unique_id()] = provider
            except Exception as ex:  # pylint: disable=broad-except
                # Catch-all for errors instantiating the provider.
                logger.warning('Unable to instantiate provider for %s: %s',
                               hub_info, ex)
