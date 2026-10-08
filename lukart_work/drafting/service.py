                        replay = self._replay(tx, request, input_hash)
                        if replay is not None:
                            return replay
                        if tx.sequence() != request.meta.expected_case_sequence:
                            raise Violation('CONFLICT')
                        (
                            _,
                            _,
                            snapshot,
                            _,
                            sections,
                            _,
                            _,
                        ) = self._context(
                            request, principal, tx, evaluation_date
                        )
                        invocations = self._invocations(
                            request, principal, snapshot, sections, profile,
                            evaluation_date,
                        )

                    results = []
                    execution_receipts = []
                    raw_outputs = []
                    for index, invocation in enumerate(invocations):
                        attempted = invocations[:index + 1]
                        try:
                            raw_value = self.model_provider.propose(invocation)
                            serializable = (
                                raw_value.model_dump(mode='json')
                                if hasattr(raw_value, 'model_dump')
                                else raw_value
                            )
                            raw_json = json.dumps(
                                serializable, sort_keys=True, separators=(',', ':'),
                                ensure_ascii=False, allow_nan=False,
                            )
                            if len(raw_json.encode('utf-8')) > 2_000_000:
                                raise Violation('SCHEMA_INVALID')
                            raw_outputs.append(raw_json)
                            receipt = self._execution_receipt(
                                profile,
                                invocation,
                                self.model_provider.execution_receipt(
                                    invocation.request.request_id
                                ),
                            )
                            execution_receipts.append(receipt)
                            result = wire.AIResult.model_validate_json(raw_json)
                            results.append(result)
                            if result.disposition == 'ABSTAIN':
                                return self._record_abstain(
                                    request, principal, input_hash, profile,
                                    invocations, tuple(results),
                                    tuple(execution_receipts), tuple(raw_outputs),
                                    evaluation_date,
                                )
                        except Violation as error:
                            return self._record_rejection(
                                request, principal, input_hash, profile, attempted,
                                tuple(results), tuple(execution_receipts),
                                tuple(raw_outputs),
                                safe_error(error.code, correlation),
                                invocation.request.request_id,
                            )
                        except (
                            ValidationError, ValueError, TypeError, KeyError,
                            RecursionError,
                        ):
                            return self._record_rejection(
                                request, principal, input_hash, profile, attempted,
                                tuple(results), tuple(execution_receipts),
                                tuple(raw_outputs),
                                safe_error('SCHEMA_INVALID', correlation),
                                invocation.request.request_id,
                            )
                        except Exception:
                            return self._record_rejection(
                                request, principal, input_hash, profile, attempted,
                                tuple(results), tuple(execution_receipts),
                                tuple(raw_outputs),
                                safe_error('UNKNOWN', correlation),
                                invocation.request.request_id,
                            )
                    try:
                        return self._commit(
                            request, principal, input_hash, profile,
                            invocations, tuple(results),
                            tuple(execution_receipts), tuple(raw_outputs),
                            evaluation_date,
                        )
                    except Violation as error:
                        return self._record_rejection(
                            request, principal, input_hash, profile, invocations,
                            tuple(results), tuple(execution_receipts),
                            tuple(raw_outputs),
                            safe_error(error.code, correlation),
                            None,
                        )
                    except (
                        ValidationError, ValueError, TypeError, KeyError,
                        RecursionError,
                    ):
                        return self._record_rejection(
                            request, principal, input_hash, profile, invocations,
                            tuple(results), tuple(execution_receipts),