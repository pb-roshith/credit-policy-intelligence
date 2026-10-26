import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.database import account_user_id
from app.security import current_user


class SelectedAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_cannot_select_another_account(self):
        request = SimpleNamespace(headers={'X-Account-User-Id': 'other'})
        actor = {'user_id': 'manager', 'role': 'relationship_manager'}
        with patch('app.security.resolve_session', return_value=('', {'user': actor})):
            with self.assertRaises(HTTPException) as error:
                await anext(current_user(request))
        self.assertEqual(error.exception.status_code, 403)

    async def test_analyst_selects_verified_manager_and_context_is_restored(self):
        request = SimpleNamespace(headers={'X-Account-User-Id': 'manager_b'})
        actor = {'user_id': 'analyst', 'role': 'credit_analyst'}
        previous = account_user_id.get()
        with patch('app.security.resolve_session', return_value=('', {'user': actor})), patch('app.security.db_connection') as factory, patch('app.security.ensure_account_defaults'):
            factory.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'value': 1}
            dependency = current_user(request)
            self.assertEqual(await anext(dependency), actor)
            self.assertEqual(account_user_id.get(), 'manager_b')
            await dependency.aclose()
            self.assertEqual(account_user_id.get(), previous)

    async def test_analyst_cannot_select_non_manager(self):
        request = SimpleNamespace(headers={'X-Account-User-Id': 'unknown'})
        actor = {'user_id': 'analyst', 'role': 'credit_analyst'}
        with patch('app.security.resolve_session', return_value=('', {'user': actor})), patch('app.security.db_connection') as factory:
            factory.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            with self.assertRaises(HTTPException) as error:
                await anext(current_user(request))
            self.assertEqual(error.exception.status_code, 404)
