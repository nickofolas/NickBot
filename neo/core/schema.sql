CREATE TYPE counting AS ( channel_id BIGINT, current_number BIGINT );

CREATE TABLE user_data (
    user_id BIGINT PRIMARY KEY, 
    repr_errors   BOOLEAN  DEFAULT FALSE,
    error_emojis  BOOLEAN  DEFAULT FALSE,
    hl_blocks     BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    hl_whitelist  BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    can_snipe     BOOLEAN  DEFAULT TRUE,
    _blacklisted  BOOLEAN  DEFAULT FALSE
);

CREATE TABLE highlights (
    user_id BIGINT NOT NULL,
    kw TEXT NOT NULL,
    is_regex BOOLEAN DEFAULT TRUE,
    PRIMARY KEY(user_id, kw, is_regex)
);

CREATE TABLE reminders (
    user_id  BIGINT NOT NULL,
    content  VARCHAR(200) DEFAULT '...',
    deadline TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    id       BIGINT NOT NULL,
    origin_jump TEXT
);

CREATE TABLE guild_prefs (
    guild_id     BIGINT PRIMARY KEY NOT NULL,
    prefixes     TEXT[] DEFAULT ARRAY[]::TEXT[],
    index_emojis BOOLEAN DEFAULT TRUE,
    snipes       BOOLEAN DEFAULT FALSE,
    starboard    BOOLEAN DEFAULT FALSE,
    starboard_star_requirement BIGINT DEFAULT 5,
    starboard_channel_id BIGINT,
    starboard_format VARCHAR(200) DEFAULT ':star: **{stars}**',
    starboard_max_days BIGINT CHECK (starboard_max_days > 1) DEFAULT 7,
    counting_channel counting
);

CREATE TABLE starboard_msgs (
    message_id  BIGINT NOT NULL,
    channel_id  BIGINT NOT NULL,
    guild_id    BIGINT NOT NULL,
    stars       BIGINT,
    starred_message_id BIGINT,
    PRIMARY KEY (message_id, channel_id, guild_id)
);

CREATE TABLE todo (
    user_id bigint NOT NULL,
    content TEXT NOT NULL,
    jump_url TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE OR REPLACE FUNCTION change_starboard(new_destination BIGINT, _guild_id BIGINT) RETURNS void AS $$
BEGIN
        DELETE FROM starboard_msgs WHERE starboard_msgs.guild_id = _guild_id;
        UPDATE guild_prefs 
        SET starboard_channel_id = new_destination
        WHERE guild_prefs.guild_id = _guild_id;
END;
$$ LANGUAGE plpgsql;