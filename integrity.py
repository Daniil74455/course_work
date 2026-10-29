import hashlib
from datetime import datetime
from encryption import compute_hmac_signature, verify_hmac_signature

GENESIS_PREV_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

def format_exam_payload(student_id: int, exam_type: str, score: int, is_passed: bool,
                        passed_at: datetime, examiner_id: int) -> str:
    """Формирует каноническую строку экзамена для вычисления хеша и HMAC-подписи."""
    date_str = passed_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(passed_at, datetime) else str(passed_at)
    return f"{student_id}|{exam_type}|{score}|{1 if is_passed else 0}|{date_str}|{examiner_id}"

def calculate_chain_hash(payload: str, prev_hash: str) -> str:
    """Вычисляет блокчейн-хеш записи SHA-256 (payload + prev_hash)."""
    raw = f"{payload}|{prev_hash}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def check_exam_ledger_integrity(exams_list) -> dict:
    """
    Выполняет полную криптографическую ревизию журнала экзаменов:
    1. Проверка HMAC-SHA256 подписи каждого протокола.
    2. Проверка непрерывности блокчейн-цепочки хешей (prev_hash -> record_hash).
    """
    total = len(exams_list)
    tampered_records = []
    broken_chains = []
    valid_count = 0

    expected_prev_hash = GENESIS_PREV_HASH

    for idx, exam in enumerate(exams_list):
        payload = format_exam_payload(
            student_id=exam.student_id,
            exam_type=exam.exam_type,
            score=exam.score,
            is_passed=exam.is_passed,
            passed_at=exam.passed_at,
            examiner_id=exam.examiner_id or 0
        )

        # 1. Проверка HMAC подписи
        is_signature_valid = verify_hmac_signature(payload, exam.signature or "")

        # 2. Проверка соответствия record_hash содержимому
        computed_record_hash = calculate_chain_hash(payload, exam.prev_hash or GENESIS_PREV_HASH)
        is_hash_matching = (computed_record_hash == exam.record_hash)

        # 3. Проверка непрерывности цепочки
        is_chain_linked = (exam.prev_hash == expected_prev_hash)

        if not is_signature_valid or not is_hash_matching:
            tampered_records.append({
                'id': exam.id,
                'student_id': exam.student_id,
                'exam_type': exam.exam_type,
                'score': exam.score,
                'is_passed': exam.is_passed,
                'passed_at': exam.passed_at,
                'reason': 'Подделка данных протокола: цифровая подпись HMAC не совпадает с содержимым!'
            })

        if not is_chain_linked and idx > 0:
            broken_chains.append({
                'id': exam.id,
                'expected_prev_hash': expected_prev_hash,
                'actual_prev_hash': exam.prev_hash,
                'reason': 'Нарушение хронологической целостности БД: разрыв блокчейн-цепочки хешей!'
            })

        if is_signature_valid and is_hash_matching and (is_chain_linked or idx == 0):
            valid_count += 1

        expected_prev_hash = exam.record_hash

    is_all_clean = (len(tampered_records) == 0 and len(broken_chains) == 0)

    return {
        'total': total,
        'valid_count': valid_count,
        'tampered_count': len(tampered_records),
        'chain_breaks_count': len(broken_chains),
        'is_healthy': is_all_clean,
        'tampered_records': tampered_records,
        'broken_chains': broken_chains
    }
