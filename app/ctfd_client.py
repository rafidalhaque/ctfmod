"""
CTFd API Client with comprehensive validation, error handling, and logging.
"""
import logging
import requests
from typing import Dict, Any, Optional, List
from enum import Enum


# Configure logger
logger = logging.getLogger(__name__)


class CTFdErrorType(Enum):
    """Types of CTFd API errors for better error handling."""
    CONFIGURATION_ERROR = "configuration_error"
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"
    API_ERROR = "api_error"
    RESPONSE_VALIDATION_ERROR = "response_validation_error"


class CTFdAPIException(Exception):
    """Custom exception for CTFd API errors."""
    
    def __init__(self, message: str, error_type: CTFdErrorType, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.error_type = error_type
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON responses."""
        return {
            'error': self.message,
            'error_type': self.error_type.value,
            'details': self.details
        }


class CTFdAPIClient:
    """
    Client for interacting with CTFd API with comprehensive validation and error handling.
    
    Features:
    - Input validation for all fields
    - Structured logging for debugging
    - Response validation
    - Transaction-like behavior with rollback
    - Support for additional CTFd fields
    """
    
    # Required fields for challenge creation
    REQUIRED_FIELDS = ['name', 'category', 'description', 'value', 'type']
    
    # Optional fields supported by CTFd API
    OPTIONAL_FIELDS = [
        'state', 'max_attempts', 'connection_info', 'attribution',
        'next_id', 'logic', 'initial', 'minimum', 'decay', 'function',
        'requirements', 'extra'
    ]
    
    # Valid challenge states
    VALID_STATES = ['visible', 'hidden']
    
    # Valid challenge types (standard is most common)
    VALID_TYPES = ['standard', 'dynamic']
    
    def __init__(self, ctfd_url: str, ctfd_api_key: str, timeout: int = 30):
        """
        Initialize CTFd API client.
        
        Args:
            ctfd_url: Base URL of CTFd instance
            ctfd_api_key: API key for authentication
            timeout: Request timeout in seconds
            
        Raises:
            CTFdAPIException: If configuration is invalid
        """
        self._validate_configuration(ctfd_url, ctfd_api_key)
        
        self.ctfd_url = ctfd_url.rstrip('/')
        self.ctfd_api_key = ctfd_api_key
        self.timeout = timeout
        
        self.headers = {
            'Authorization': f'Token {ctfd_api_key}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"CTFd API Client initialized for {self.ctfd_url}")
    
    def _validate_configuration(self, ctfd_url: str, ctfd_api_key: str) -> None:
        """Validate CTFd configuration."""
        if not ctfd_url:
            raise CTFdAPIException(
                "CTFd URL is required",
                CTFdErrorType.CONFIGURATION_ERROR,
                {'field': 'ctfd_url'}
            )
        
        if not ctfd_api_key:
            raise CTFdAPIException(
                "CTFd API key is required",
                CTFdErrorType.CONFIGURATION_ERROR,
                {'field': 'ctfd_api_key'}
            )
        
        if not ctfd_url.startswith(('http://', 'https://')):
            raise CTFdAPIException(
                "CTFd URL must start with http:// or https://",
                CTFdErrorType.CONFIGURATION_ERROR,
                {'field': 'ctfd_url', 'value': ctfd_url}
            )
    
    def _validate_challenge_data(self, challenge_data: Dict[str, Any]) -> None:
        """
        Validate challenge data before sending to CTFd.
        
        Args:
            challenge_data: Challenge data to validate
            
        Raises:
            CTFdAPIException: If validation fails
        """
        # Check required fields
        missing_fields = []
        for field in self.REQUIRED_FIELDS:
            if field not in challenge_data or challenge_data[field] is None or challenge_data[field] == '':
                missing_fields.append(field)
        
        if missing_fields:
            raise CTFdAPIException(
                f"Missing required fields: {', '.join(missing_fields)}",
                CTFdErrorType.VALIDATION_ERROR,
                {'missing_fields': missing_fields}
            )
        
        # Validate state if provided
        if 'state' in challenge_data and challenge_data['state'] not in self.VALID_STATES:
            raise CTFdAPIException(
                f"Invalid state '{challenge_data['state']}'. Must be one of: {', '.join(self.VALID_STATES)}",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'state', 'value': challenge_data['state'], 'valid_values': self.VALID_STATES}
            )
        
        # Validate type if provided
        if 'type' in challenge_data and challenge_data['type'] not in self.VALID_TYPES:
            raise CTFdAPIException(
                f"Invalid type '{challenge_data['type']}'. Must be one of: {', '.join(self.VALID_TYPES)}",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'type', 'value': challenge_data['type'], 'valid_values': self.VALID_TYPES}
            )
        
        # Validate max_attempts if provided
        # Note: 0 means unlimited attempts in CTFd
        if 'max_attempts' in challenge_data and challenge_data['max_attempts'] is not None:
            try:
                max_attempts = int(challenge_data['max_attempts'])
                if max_attempts < 0:
                    raise ValueError("max_attempts must be non-negative (0 = unlimited)")
            except (ValueError, TypeError) as e:
                raise CTFdAPIException(
                    f"Invalid max_attempts value: {str(e)}",
                    CTFdErrorType.VALIDATION_ERROR,
                    {'field': 'max_attempts', 'value': challenge_data.get('max_attempts')}
                )
        
        # Validate value (points)
        try:
            value = int(challenge_data['value'])
            if value <= 0:
                raise ValueError("value must be positive")
        except (ValueError, TypeError) as e:
            raise CTFdAPIException(
                f"Invalid value (points): {str(e)}",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'value', 'value': challenge_data.get('value')}
            )
        
        logger.debug(f"Challenge data validation passed for '{challenge_data.get('name')}'")
    
    def _validate_response(self, response: requests.Response, operation: str) -> Dict[str, Any]:
        """
        Validate CTFd API response.
        
        Args:
            response: HTTP response from CTFd
            operation: Description of the operation for logging
            
        Returns:
            Parsed JSON response
            
        Raises:
            CTFdAPIException: If response is invalid
        """
        try:
            response_data = response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON response for {operation}: {str(e)}")
            # Don't log full response text as it may contain sensitive data
            raise CTFdAPIException(
                f"Invalid JSON response from CTFd for {operation}",
                CTFdErrorType.RESPONSE_VALIDATION_ERROR,
                {'status_code': response.status_code}
            )
        
        # CTFd typically returns success=True for successful operations
        if response.status_code not in [200, 201]:
            error_message = response_data.get('message', response_data.get('error', 'Unknown error'))
            logger.error(f"CTFd API error for {operation}: {error_message} (status: {response.status_code})")
            raise CTFdAPIException(
                f"CTFd API error: {error_message}",
                CTFdErrorType.API_ERROR,
                {
                    'status_code': response.status_code,
                    'operation': operation,
                    'response': response_data
                }
            )
        
        # Validate response structure
        if 'success' in response_data and not response_data.get('success'):
            error_message = response_data.get('message', response_data.get('error', 'Operation failed'))
            logger.error(f"CTFd operation failed for {operation}: {error_message}")
            raise CTFdAPIException(
                f"CTFd operation failed: {error_message}",
                CTFdErrorType.API_ERROR,
                {'operation': operation, 'response': response_data}
            )
        
        return response_data
    
    def create_challenge(self, challenge_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a challenge on CTFd.
        
        Args:
            challenge_data: Challenge data including name, category, description, value, type, etc.
            
        Returns:
            Dictionary with created challenge data including 'id'
            
        Raises:
            CTFdAPIException: If challenge creation fails
        """
        # Validate input
        self._validate_challenge_data(challenge_data)
        
        # Prepare challenge payload (only include known fields)
        payload = {}
        for field in self.REQUIRED_FIELDS + self.OPTIONAL_FIELDS:
            if field in challenge_data and challenge_data[field] is not None:
                payload[field] = challenge_data[field]
        
        logger.info(f"Creating challenge '{challenge_data['name']}' on CTFd")
        logger.debug(f"Challenge payload: {payload}")
        
        try:
            url = f"{self.ctfd_url}/api/v1/challenges"
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            response_data = self._validate_response(response, "challenge creation")
            
            # Extract challenge data from response
            if 'data' not in response_data:
                raise CTFdAPIException(
                    "Response missing 'data' field",
                    CTFdErrorType.RESPONSE_VALIDATION_ERROR,
                    {'response': response_data}
                )
            
            challenge_info = response_data['data']
            challenge_id = challenge_info.get('id')
            
            if not challenge_id:
                raise CTFdAPIException(
                    "Response missing challenge 'id'",
                    CTFdErrorType.RESPONSE_VALIDATION_ERROR,
                    {'response': response_data}
                )
            
            logger.info(f"Challenge '{challenge_data['name']}' created successfully with ID: {challenge_id}")
            return challenge_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during challenge creation: {str(e)}")
            raise CTFdAPIException(
                f"Network error: {str(e)}",
                CTFdErrorType.NETWORK_ERROR,
                {'operation': 'challenge creation', 'error': str(e)}
            )
    
    def create_flag(self, challenge_id: int, flag_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a flag for a challenge on CTFd.
        
        Args:
            challenge_id: ID of the challenge
            flag_data: Flag data including content, type, etc.
            
        Returns:
            Dictionary with created flag data
            
        Raises:
            CTFdAPIException: If flag creation fails
        """
        # Validate required fields for flag
        if 'content' not in flag_data or not flag_data['content']:
            raise CTFdAPIException(
                "Flag content is required",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'content'}
            )
        
        if 'type' not in flag_data or not flag_data['type']:
            raise CTFdAPIException(
                "Flag type is required",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'type'}
            )
        
        payload = {
            'challenge_id': challenge_id,
            'content': flag_data['content'],
            'type': flag_data['type']
        }
        
        # Add optional flag data
        if 'data' in flag_data:
            payload['data'] = flag_data['data']
        
        logger.info(f"Creating flag for challenge ID {challenge_id}")
        logger.debug(f"Flag type: {flag_data['type']}")
        
        try:
            url = f"{self.ctfd_url}/api/v1/flags"
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            response_data = self._validate_response(response, "flag creation")
            
            logger.info(f"Flag created successfully for challenge ID {challenge_id}")
            return response_data.get('data', {})
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during flag creation: {str(e)}")
            raise CTFdAPIException(
                f"Network error: {str(e)}",
                CTFdErrorType.NETWORK_ERROR,
                {'operation': 'flag creation', 'error': str(e)}
            )
    
    def delete_challenge(self, challenge_id: int) -> None:
        """
        Delete a challenge from CTFd (used for rollback).
        
        Args:
            challenge_id: ID of the challenge to delete
            
        Raises:
            CTFdAPIException: If deletion fails
        """
        logger.info(f"Deleting challenge ID {challenge_id} (rollback)")
        
        try:
            url = f"{self.ctfd_url}/api/v1/challenges/{challenge_id}"
            response = requests.delete(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            
            # Check both status code and response body for delete operations
            if response.status_code in [200, 204]:
                # Try to parse response to check for success field
                try:
                    response_data = response.json()
                    if 'success' in response_data and not response_data.get('success'):
                        logger.warning(f"Challenge deletion reported failure in response body: {response_data.get('message', 'Unknown error')}")
                    else:
                        logger.info(f"Challenge {challenge_id} deleted successfully")
                except ValueError:
                    # 204 No Content won't have a body
                    logger.info(f"Challenge {challenge_id} deleted successfully")
            else:
                logger.warning(f"Failed to delete challenge {challenge_id} during rollback: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error during challenge deletion (rollback): {str(e)}")
            # Don't raise exception during rollback to avoid masking original error
    
    def push_challenge_with_flag(
        self,
        challenge_data: Dict[str, Any],
        flag_content: Optional[str] = None,
        flag_type: str = 'static'
    ) -> Dict[str, Any]:
        """
        Create a challenge and optionally add a flag in a transaction-like manner.
        If flag creation fails, the challenge is rolled back (deleted).
        
        Args:
            challenge_data: Challenge data
            flag_content: Optional flag content
            flag_type: Flag type (default: 'static')
            
        Returns:
            Dictionary with challenge and flag information
            
        Raises:
            CTFdAPIException: If operation fails
        """
        challenge_info = None
        
        try:
            # Create challenge
            challenge_info = self.create_challenge(challenge_data)
            challenge_id = challenge_info['id']
            
            # Create flag if provided
            flag_info = None
            if flag_content:
                flag_data = {
                    'content': flag_content,
                    'type': flag_type
                }
                flag_info = self.create_flag(challenge_id, flag_data)
            
            return {
                'challenge': challenge_info,
                'flag': flag_info,
                'success': True
            }
            
        except CTFdAPIException as e:
            # If we created a challenge but flag creation failed, rollback
            if challenge_info and challenge_info.get('id'):
                logger.error(f"Rolling back challenge {challenge_info['id']} due to error: {e.message}")
                try:
                    self.delete_challenge(challenge_info['id'])
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {str(rollback_error)}")
            
            # Re-raise the original exception
            raise
    
    def create_team(self, team_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a team on CTFd.
        
        Args:
            team_data: Team data including name and password
            
        Returns:
            Dictionary with created team data including 'id'
            
        Raises:
            CTFdAPIException: If team creation fails
        """
        # Validate required fields
        if not team_data.get('name'):
            raise CTFdAPIException(
                "Team name is required",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'name'}
            )
        
        if not team_data.get('password'):
            raise CTFdAPIException(
                "Team password is required",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'password'}
            )
        
        payload = {
            'name': team_data['name'],
            'password': team_data['password'],
            'hidden': team_data.get('hidden', False),
            'banned': team_data.get('banned', False)
        }
        
        # Add optional fields
        if team_data.get('email'):
            payload['email'] = team_data['email']
        if team_data.get('affiliation'):
            payload['affiliation'] = team_data['affiliation']
        if team_data.get('country'):
            payload['country'] = team_data['country']
        
        logger.info(f"Creating team '{team_data['name']}' on CTFd")
        
        try:
            url = f"{self.ctfd_url}/api/v1/teams"
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            response_data = self._validate_response(response, "team creation")
            
            if 'data' not in response_data:
                raise CTFdAPIException(
                    "Response missing 'data' field",
                    CTFdErrorType.RESPONSE_VALIDATION_ERROR,
                    {'response': response_data}
                )
            
            team_info = response_data['data']
            team_id = team_info.get('id')
            
            if not team_id:
                raise CTFdAPIException(
                    "Response missing team 'id'",
                    CTFdErrorType.RESPONSE_VALIDATION_ERROR,
                    {'response': response_data}
                )
            
            logger.info(f"Team '{team_data['name']}' created successfully with ID: {team_id}")
            return team_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during team creation: {str(e)}")
            raise CTFdAPIException(
                f"Network error: {str(e)}",
                CTFdErrorType.NETWORK_ERROR,
                {'operation': 'team creation', 'error': str(e)}
            )
    
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a user on CTFd.
        
        Args:
            user_data: User data including name, email, and password
            
        Returns:
            Dictionary with created user data including 'id'
            
        Raises:
            CTFdAPIException: If user creation fails
        """
        # Validate required fields
        if not user_data.get('name'):
            raise CTFdAPIException(
                "User name is required",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'name'}
            )
        
        if not user_data.get('email'):
            raise CTFdAPIException(
                "User email is required",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'email'}
            )
        
        if not user_data.get('password'):
            raise CTFdAPIException(
                "User password is required",
                CTFdErrorType.VALIDATION_ERROR,
                {'field': 'password'}
            )
        
        payload = {
            'name': user_data['name'],
            'email': user_data['email'],
            'password': user_data['password'],
            'type': user_data.get('type', 'user'),
            'verified': user_data.get('verified', True),
            'hidden': user_data.get('hidden', False),
            'banned': user_data.get('banned', False)
        }
        
        # Add optional fields
        if user_data.get('affiliation'):
            payload['affiliation'] = user_data['affiliation']
        if user_data.get('country'):
            payload['country'] = user_data['country']
        
        logger.info(f"Creating user '{user_data['email']}' on CTFd")
        
        try:
            url = f"{self.ctfd_url}/api/v1/users"
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            response_data = self._validate_response(response, "user creation")
            
            if 'data' not in response_data:
                raise CTFdAPIException(
                    "Response missing 'data' field",
                    CTFdErrorType.RESPONSE_VALIDATION_ERROR,
                    {'response': response_data}
                )
            
            user_info = response_data['data']
            user_id = user_info.get('id')
            
            if not user_id:
                raise CTFdAPIException(
                    "Response missing user 'id'",
                    CTFdErrorType.RESPONSE_VALIDATION_ERROR,
                    {'response': response_data}
                )
            
            logger.info(f"User '{user_data['email']}' created successfully with ID: {user_id}")
            return user_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during user creation: {str(e)}")
            raise CTFdAPIException(
                f"Network error: {str(e)}",
                CTFdErrorType.NETWORK_ERROR,
                {'operation': 'user creation', 'error': str(e)}
            )
    
    def add_user_to_team(self, team_id: int, user_id: int) -> Dict[str, Any]:
        """
        Add a user to a team on CTFd.
        
        Args:
            team_id: ID of the team
            user_id: ID of the user to add
            
        Returns:
            Dictionary with operation result
            
        Raises:
            CTFdAPIException: If adding user to team fails
        """
        logger.info(f"Adding user {user_id} to team {team_id} on CTFd")
        
        try:
            url = f"{self.ctfd_url}/api/v1/teams/{team_id}/members"
            payload = {'user_id': user_id}
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            
            response_data = self._validate_response(response, "add user to team")
            
            logger.info(f"User {user_id} added to team {team_id} successfully")
            return response_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during add user to team: {str(e)}")
            raise CTFdAPIException(
                f"Network error: {str(e)}",
                CTFdErrorType.NETWORK_ERROR,
                {'operation': 'add user to team', 'error': str(e)}
            )
    
    def delete_team(self, team_id: int) -> None:
        """
        Delete a team from CTFd.
        
        Args:
            team_id: ID of the team to delete
        """
        logger.info(f"Deleting team ID {team_id} from CTFd")
        
        try:
            url = f"{self.ctfd_url}/api/v1/teams/{team_id}"
            response = requests.delete(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Team {team_id} deleted successfully")
            else:
                logger.warning(f"Failed to delete team {team_id}: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error during team deletion: {str(e)}")
    
    def delete_user(self, user_id: int) -> None:
        """
        Delete a user from CTFd.
        
        Args:
            user_id: ID of the user to delete
        """
        logger.info(f"Deleting user ID {user_id} from CTFd")
        
        try:
            url = f"{self.ctfd_url}/api/v1/users/{user_id}"
            response = requests.delete(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"User {user_id} deleted successfully")
            else:
                logger.warning(f"Failed to delete user {user_id}: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error during user deletion: {str(e)}")
