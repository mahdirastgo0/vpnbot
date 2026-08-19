# در فایل my_configs.py

@router.callback_query(ConfigListCallback.filter())
async def show_config(
    callback: CallbackQuery,
    callback_data: ConfigListCallback,
    session: AsyncSession,
    user: User,
    bot: Bot,
):
    # ... دریافت vpn_config از دیتابیس
    vpn_config = await session.get(VpnConfig, callback_data.config_id)
    if not vpn_config:
        await callback.answer("کانفیگ یافت نشد.", show_alert=True)
        return

    # اصلاح: استفاده از config_name به عنوان کلید
    caption = texts.CONFIG_QR_CAPTION.format(
        config_name=vpn_config.config_name,          # <-- کلید درست
        plan_name=vpn_config.plan_name,
        expire_at=vpn_config.expire_at.strftime("%Y-%m-%d %H:%M"),
        traffic_gb=vpn_config.traffic_gb,
        # سایر متغیرها ...
    )

    # ... ارسال عکس QR یا پیام