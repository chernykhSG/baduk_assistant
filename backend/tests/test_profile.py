from baduk_backend.config.profile import KataGoProfile, render_analysis_config


def test_render_analysis_config_includes_thread_and_visit_settings():
    profile = KataGoProfile(
        model_id="kata1-b28c512nbt",
        display_name="Default profile",
        rules="chinese",
        board_size=19,
        komi=7.5,
        max_visits=50,
        num_analysis_threads=2,
    )
    config_text = render_analysis_config(profile)
    assert "numAnalysisThreads = 2" in config_text
    assert "numSearchThreads = 2" in config_text
    assert "maxVisits = 50" in config_text
