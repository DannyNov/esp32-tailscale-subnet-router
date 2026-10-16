"""Experimental serialized lifecycle overlay. Never writes pinned upstream."""
from pathlib import Path
import re


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('checked destroy anchor mismatch: ' + old[:80])
    return text.replace(old, new, 1)


def apply(component: Path):
    source = component / 'src/microlink.c'
    text = source.read_text(encoding='utf-8')
    # A stopped instance owns stale queues/events; require destroy/re-init.
    text = once(text, '    if (ml->state != ML_STATE_IDLE) {',
                '    if (ml->state != ML_STATE_IDLE ||\n'
                '        (xEventGroupGetBits(ml->events) & ML_EVT_SHUTDOWN_REQUEST)) {')
    # Reserve before scheduling: a new task may exit before create returns.
    pattern = (r'    ret = xTaskCreatePinnedToCore\((.*?)'
               r'    __atomic_add_fetch\(&ml->tasks_alive, 1, __ATOMIC_SEQ_CST\);')
    def reserve(match):
        body = match.group(1)
        body = once(body, '    if (ret != pdPASS) {',
                    '    if (ret != pdPASS) {\n'
                    '        __atomic_sub_fetch(&ml->tasks_alive, 1, __ATOMIC_SEQ_CST);\n'
                    '        xEventGroupSetBits(ml->events, ML_EVT_SHUTDOWN_REQUEST);')
        return ('    __atomic_add_fetch(&ml->tasks_alive, 1, __ATOMIC_SEQ_CST);\n'
                '    ret = xTaskCreatePinnedToCore(' + body)
    text, count = re.subn(pattern, reserve, text, flags=re.S)
    if count != 5:
        raise RuntimeError('Expected five task reservations')
    text = once(text, '            ml->stop_incomplete = true;',
                '            ml->stop_incomplete = true;\n'
                '            return ESP_ERR_TIMEOUT; /* retain ALL shared resources */')
    text = once(text, 'void microlink_destroy(microlink_t *ml) {\n    if (!ml) return;\n\n    microlink_stop(ml);',
                'esp_err_t microlink_destroy_checked(microlink_t **owner) {\n'
                '    if (!owner) return ESP_ERR_INVALID_ARG;\n'
                '    microlink_t *ml = *owner;\n'
                '    if (!ml) return ESP_OK;\n'
                '    esp_err_t stopped = microlink_stop(ml);\n'
                '    if (stopped != ESP_OK) return stopped;')
    text = once(text, '        return;\n    }\n    /* Only now',
                '        return ESP_ERR_TIMEOUT;\n    }\n    /* Only now')
    text = once(text, '    ESP_LOGI(TAG, "Destroyed");\n}',
                '    *owner = NULL;\n'
                '    ESP_LOGI(TAG, "Destroyed");\n'
                '    return ESP_OK;\n}\n\n'
                'void microlink_destroy(microlink_t *ml) {\n'
                '    /* Compatibility only; manager uses the checked owner API. */\n'
                '    (void)microlink_destroy_checked(&ml);\n}')
    source.write_text(text, encoding='utf-8')
    header = component / 'include/microlink.h'
    text = header.read_text(encoding='utf-8')
    text = once(text, 'void microlink_destroy(microlink_t *ml);',
                '/* Caller serializes start/stop/destroy and drains external readers.\n'
                ' * Failure preserves *owner and its resources; success clears it. */\n'
                'esp_err_t microlink_destroy_checked(microlink_t **owner);\n'
                'void microlink_destroy(microlink_t *ml);')
    header.write_text(text, encoding='utf-8')
