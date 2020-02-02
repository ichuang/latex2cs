calc = cs_local_python_import("{calc}")
general_hint_system = cs_local_python_import("{general_hint_system}")
general_hint_system.evaluator = calc.evaluator
general_hint_system.ParseAugmenter = calc.ParseAugmenter
general_hint_system.latex_preview = calc.latex_preview
