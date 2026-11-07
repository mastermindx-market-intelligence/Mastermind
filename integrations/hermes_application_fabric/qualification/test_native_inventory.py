"""Native shared inventory for host-managed providers, with no credential discovery."""
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace as N
from unittest.mock import Mock, patch
import unittest


class HostBoundInventoryTests(unittest.TestCase):
    slug = "fixture-host"
    model = "fixture-host/auto"

    @contextmanager
    def inventory(self, catalog):
        from hermes_cli import inventory
        from providers.base import ProviderProfile
        profile = ProviderProfile(name=self.slug, api_mode="chat_completions",
            host_bound_runtime=True, picker_catalog=catalog, static_models=(self.model,))
        entries = [N(slug=self.slug, label="Fixture Host")]
        with ExitStack() as stack:
            stack.enter_context(patch("providers.get_provider_profile",
                side_effect=lambda slug: profile if slug == self.slug else None))
            stack.enter_context(patch("hermes_cli.models_catalog_static.listed_canonical_providers",
                                      return_value=entries))
            stack.enter_context(patch("hermes_cli.models._PROVIDER_ALIASES",
                                      {"fixture-alias": self.slug}))
            stack.enter_context(patch("hermes_cli.model_switch.list_authenticated_providers",
                                      return_value=[]))
            stack.enter_context(patch.object(inventory, "_local_runtime_row", return_value=None))
            stack.enter_context(patch.object(inventory, "_moa_provider_row", return_value=None))
            yield inventory

    def context(self, *, provider=None, configured=None, excluded=None):
        from hermes_cli.inventory import ConfigContext
        return ConfigContext(current_provider=self.slug if provider is None else provider,
            current_model=self.model, current_base_url="", user_providers=configured or {},
            custom_providers=[], excluded_providers=excluded or [])

    def test_eligible_catalog_is_selectable_without_claiming_authentication(self):
        catalog = Mock(return_value=[self.model])
        with self.inventory(catalog) as inventory:
            result = inventory.build_models_payload(self.context(), picker_hints=True,
                                                    explicit_only=True, refresh=True)
        row, = result["providers"]
        self.assertEqual(row["models"], [self.model])
        self.assertEqual((row["source"], row["authenticated"], row["key_env"]),
                         ("host-bound", False, ""))
        self.assertIn("checked on each turn", row["warning"])
        catalog.assert_called_once_with(True)

    def test_held_current_host_never_resurrects_the_saved_model(self):
        for catalog in (None, Mock(return_value=[]), Mock(return_value=None),
                        Mock(side_effect=RuntimeError("unavailable"))):
            with self.subTest(catalog=catalog), self.inventory(catalog) as inventory:
                result = inventory.build_models_payload(self.context(), picker_hints=True,
                    explicit_only=True, include_unconfigured=True)
                row, = result["providers"]
                self.assertEqual((row["models"], row["total_models"]), ([], 0))
                self.assertEqual((row["source"], row["authenticated"]), ("host-bound", False))
                self.assertIn("Host setup is unavailable", row["warning"])
                self.assertNotIn("credentials", row["warning"])

    def test_excluded_host_and_alias_stay_hidden_even_when_current(self):
        for excluded in ([self.slug], ["fixture-alias"]):
            with self.subTest(excluded=excluded):
                catalog = Mock(return_value=[self.model])
                with self.inventory(catalog) as inventory:
                    result = inventory.build_models_payload(self.context(excluded=excluded),
                        explicit_only=True, include_unconfigured=True, picker_hints=True)
                self.assertEqual(result["providers"], [])
                catalog.assert_not_called()

    def test_disabled_host_and_alias_stay_hidden_even_when_current(self):
        for key in (self.slug, "fixture-alias"):
            catalog = Mock(return_value=[self.model])
            with self.subTest(key=key), self.inventory(catalog) as inventory:
                result = inventory.build_models_payload(
                    self.context(configured={key: {"enabled": False}}),
                    explicit_only=True, include_unconfigured=True)
            self.assertEqual(result["providers"], [])
            catalog.assert_not_called()

    def test_host_source_does_not_bypass_explicit_configuration_policy(self):
        with self.inventory(Mock(return_value=[self.model])) as inventory:
            with patch("hermes_cli.auth.is_provider_explicitly_configured", return_value=False):
                self.assertEqual(inventory.build_models_payload(
                    self.context(provider="unrelated"), explicit_only=True)["providers"], [])
            with patch("hermes_cli.auth.is_provider_explicitly_configured", return_value=True):
                rows = inventory.build_models_payload(
                    self.context(provider="unrelated"), explicit_only=True)["providers"]
                self.assertEqual([row["slug"] for row in rows], [self.slug])

    def test_invalid_catalog_cannot_fall_back_to_static_or_saved_choices(self):
        for observed in ({"models": [self.model]}, [None], [" "], [" model "]):
            with self.subTest(observed=observed), self.inventory(Mock(return_value=observed)) as inventory:
                rows = inventory.build_models_payload(self.context(), include_unconfigured=True)["providers"]
                self.assertEqual(rows[0]["models"], [])


if __name__ == "__main__":
    unittest.main()
