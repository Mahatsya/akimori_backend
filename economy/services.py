# services.py
from __future__ import annotations

from typing import Tuple

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    Wallet,
    Transaction,
    TxType,
    normalize_amount,
    InsufficientFunds,
    Currency,
    TransferResult,
)


def ensure_user_wallets(user) -> Tuple[Wallet, Wallet]:
    """Гарантируем по одному кошельку RUB и AKI."""
    rub, _ = Wallet.objects.get_or_create(user=user, currency=Currency.RUB)
    aki, _ = Wallet.objects.get_or_create(user=user, currency=Currency.AKI)
    return rub, aki


@transaction.atomic
def deposit(
    wallet: Wallet,
    amount: int | str | float,
    *,
    description: str = "",
    idempotency_key: str | None = None,
) -> Transaction:
    """Пополнение кошелька с защитой от задвоения (idempotency)."""
    amt = normalize_amount(wallet.currency, amount)

    if idempotency_key:
        existing = Transaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            # Безопасная проверка: совпадают ли параметры?
            if (
                existing.wallet_id != wallet.id
                or existing.tx_type != TxType.DEPOSIT
                or existing.amount != amt
            ):
                raise ValidationError("Idempotency key already used for another operation")
            return existing

    # Перечитываем кошелёк с блокировкой
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    wallet.balance = wallet.balance + amt
    wallet.save(update_fields=["balance", "updated_at"])

    tx = Transaction.objects.create(
        wallet=wallet,
        tx_type=TxType.DEPOSIT,
        amount=amt,
        description=description or "Пополнение",
        idempotency_key=idempotency_key,
    )
    return tx


@transaction.atomic
def withdraw(
    wallet: Wallet,
    amount: int | str | float,
    *,
    description: str = "",
    idempotency_key: str | None = None,
) -> Transaction:
    """Списание с кошелька с проверкой баланса и idempotency."""
    amt = normalize_amount(wallet.currency, amount)

    if idempotency_key:
        existing = Transaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if (
                existing.wallet_id != wallet.id
                or existing.tx_type != TxType.WITHDRAW
                or existing.amount != amt
            ):
                raise ValidationError("Idempotency key already used for another operation")
            return existing

    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)

    if not wallet.can_debit(amt):
        raise InsufficientFunds("Недостаточно средств")

    wallet.balance = wallet.balance - amt
    wallet.save(update_fields=["balance", "updated_at"])

    tx = Transaction.objects.create(
        wallet=wallet,
        tx_type=TxType.WITHDRAW,
        amount=amt,
        description=description or "Списание",
        idempotency_key=idempotency_key,
    )
    return tx


@transaction.atomic
def transfer(
    from_wallet: Wallet,
    to_wallet: Wallet,
    amount: int | str | float,
    *,
    description: str = "",
    idem_out: str | None = None,
    idem_in: str | None = None,
) -> TransferResult:
    """
    Перевод между кошельками одной валюты.

    Идемпотентность:
      - если передан idem_out и уже есть TRANSFER_OUT с таким ключом,
        возвращаем готовый результат, проверив параметры.
    """
    if from_wallet.currency != to_wallet.currency:
        raise ValidationError("Перевод возможен только в рамках одной валюты")

    if from_wallet.pk == to_wallet.pk:
        raise ValidationError("Нельзя переводить самому себе на тот же кошелёк")

    amt = normalize_amount(from_wallet.currency, amount)

    # Проверка идемпотентности OUT-транзакции
    if idem_out:
        existing_out = Transaction.objects.select_related("related_tx").filter(
            idempotency_key=idem_out,
            tx_type=TxType.TRANSFER_OUT,
        ).first()
        if existing_out:
            # Параметры должны совпадать
            if existing_out.wallet_id != from_wallet.id or existing_out.amount != amt:
                raise ValidationError("Idempotency key already used for another operation")

            existing_in = existing_out.related_tx
            return TransferResult(
                out_tx=existing_out,
                in_tx=existing_in,
                amount=existing_out.amount,
            )

    # Лочим оба кошелька в стабильном порядке, чтобы не ловить deadlock
    w_ids = sorted([from_wallet.pk, to_wallet.pk])
    wallets = {
        w.pk: w
        for w in Wallet.objects.select_for_update().filter(pk__in=w_ids)
    }
    from_wallet = wallets[from_wallet.pk]
    to_wallet = wallets[to_wallet.pk]

    if not from_wallet.can_debit(amt):
        raise InsufficientFunds("Недостаточно средств для перевода")

    # OUT
    from_wallet.balance = from_wallet.balance - amt
    from_wallet.save(update_fields=["balance", "updated_at"])
    out_tx = Transaction.objects.create(
        wallet=from_wallet,
        tx_type=TxType.TRANSFER_OUT,
        amount=amt,
        description=description or f"Перевод → {to_wallet.user_id}",
        idempotency_key=idem_out,
    )

    # IN
    to_wallet.balance = to_wallet.balance + amt
    to_wallet.save(update_fields=["balance", "updated_at"])
    in_tx = Transaction.objects.create(
        wallet=to_wallet,
        tx_type=TxType.TRANSFER_IN,
        amount=amt,
        description=description or f"Перевод от {from_wallet.user_id}",
        idempotency_key=idem_in,
        related_tx=out_tx,
    )

    out_tx.related_tx = in_tx
    out_tx.save(update_fields=["related_tx"])

    return TransferResult(out_tx=out_tx, in_tx=in_tx, amount=amt)
