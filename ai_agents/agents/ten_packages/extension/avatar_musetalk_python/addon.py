#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_runtime import Addon, LogLevel, TenEnv, register_addon_as_extension


@register_addon_as_extension("avatar_musetalk_python")
class AvatarMuseTalkExtensionAddon(Addon):
    def on_create_instance(
        self, ten_env: TenEnv, name: str, context: object
    ) -> None:
        try:
            from .extension import AvatarMuseTalkExtension
        except Exception:  # Loaded as top-level module by addon loader.
            from extension import AvatarMuseTalkExtension

        ten_env.log(LogLevel.INFO, "on_create_instance")
        ten_env.on_create_instance_done(AvatarMuseTalkExtension(name), context)
