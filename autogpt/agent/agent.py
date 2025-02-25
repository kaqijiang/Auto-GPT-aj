from colorama import Fore, Style
from autogpt.app import execute_command, get_command

from autogpt.chat import chat_with_ai, create_chat_message
from autogpt.config import Config
from autogpt.json_fixes.bracket_termination import (
    attempt_to_fix_json_by_finding_outermost_brackets,
)
from autogpt.logs import logger, print_assistant_thoughts
from autogpt.speech import say_text
from autogpt.spinner import Spinner
from autogpt.utils import clean_input


class Agent:
    """Agent class for interacting with Auto-GPT.

    Attributes:
        ai_name: The name of the agent.
        memory: The memory object to use.
        full_message_history: The full message history.
        next_action_count: The number of actions to execute.
        prompt: The prompt to use.
        user_input: The user input.

    """

    def __init__(
        self,
        ai_name,
        memory,
        full_message_history,
        next_action_count,
        prompt,
        user_input,
    ):
        self.ai_name = ai_name
        self.memory = memory
        self.full_message_history = full_message_history
        self.next_action_count = next_action_count
        self.prompt = prompt
        self.user_input = user_input

    def start_interaction_loop(self):
        # Interaction Loop
        cfg = Config()
        loop_count = 0
        command_name = None
        arguments = None
        while True:
            # Discontinue if continuous limit is reached
            loop_count += 1
            if (
                cfg.continuous_mode
                and cfg.continuous_limit > 0
                and loop_count > cfg.continuous_limit
            ):
                logger.typewriter_log(
                    "连续达到限制: ", Fore.YELLOW, f"{cfg.continuous_limit}"
                )
                break

            # Send message to AI, get response
            with Spinner("Thinking... "):
                assistant_reply = chat_with_ai(
                    self.prompt,
                    self.user_input,
                    self.full_message_history,
                    self.memory,
                    cfg.fast_token_limit,
                )  # TODO: This hardcodes the model to use GPT3.5. Make this an argument

            # Print Assistant thoughts
            print_assistant_thoughts(self.ai_name, assistant_reply)

            # Get command name and arguments
            try:
                command_name, arguments = get_command(
                    attempt_to_fix_json_by_finding_outermost_brackets(assistant_reply)
                )
                if cfg.speak_mode:
                    say_text(f"我要执行 {command_name}")
            except Exception as e:
                logger.error("Error: \n", str(e))

            if not cfg.continuous_mode and self.next_action_count == 0:
                ### GET USER AUTHORIZATION TO EXECUTE COMMAND ###
                # Get key press: Prompt the user to press enter to continue or escape
                # to exit
                self.user_input = ""
                logger.typewriter_log(
                    "下一步操作: ",
                    Fore.CYAN,
                    f"COMMAND = {Fore.CYAN}{command_name}{Style.RESET_ALL}"
                    f"  ARGUMENTS = {Fore.CYAN}{arguments}{Style.RESET_ALL}",
                )
                print(
                    f"输入'y'授权命令，'y -N'运行N个连续命令，'n'退出程序，或为{self.ai_name}输入反馈...",
                    flush=True)
                while True:
                    console_input = clean_input(
                        Fore.MAGENTA + "Input:" + Style.RESET_ALL
                    )
                    if console_input.lower().rstrip() == "y":
                        self.user_input = "GENERATE NEXT COMMAND JSON"
                        break
                    elif console_input.lower().startswith("y -"):
                        try:
                            self.next_action_count = abs(
                                int(console_input.split(" ")[1])
                            )
                            self.user_input = "GENERATE NEXT COMMAND JSON"
                        except ValueError:
                            print("输入格式无效。 请输入'y -n',其中 n 是连续任务的数量。 例如: y -1")
                            continue
                        break
                    elif console_input.lower() == "n":
                        self.user_input = "EXIT"
                        break
                    else:
                        self.user_input = console_input
                        command_name = "human_feedback"
                        break

                if self.user_input == "GENERATE NEXT COMMAND JSON":
                    logger.typewriter_log(
                        "-=-=-=-=-=-=-= 用户授权的命令 -=-=-=-=-=-=-=",
                        Fore.MAGENTA,
                        "",
                    )
                elif self.user_input == "EXIT":
                    print("退出中...", flush=True)
                    break
            else:
                # Print command
                logger.typewriter_log(
                    "下一步操作: ",
                    Fore.CYAN,
                    f"COMMAND = {Fore.CYAN}{command_name}{Style.RESET_ALL}"
                    f"  ARGUMENTS = {Fore.CYAN}{arguments}{Style.RESET_ALL}",
                )

            # Execute command
            if command_name is not None and command_name.lower().startswith("error"):
                result = (
                    f"Command {command_name} 抛出以下错误: {arguments}"
                )
            elif command_name == "human_feedback":
                result = f"人工反馈: {self.user_input}"
            else:
                result = (
                    f"Command {command_name} returned: "
                    f"{execute_command(command_name, arguments)}"
                )
                if self.next_action_count > 0:
                    self.next_action_count -= 1

            memory_to_add = (
                f"机器人回复: {assistant_reply} "
                f"\n结果: {result} "
                f"\n人工反馈: {self.user_input} "
            )

            self.memory.add(memory_to_add)

            # Check if there's a result from the command append it to the message
            # history
            if result is not None:
                self.full_message_history.append(create_chat_message("system", result))
                logger.typewriter_log("SYSTEM: ", Fore.YELLOW, result)
            else:
                self.full_message_history.append(
                    create_chat_message("system", "无法执行命令")
                )
                logger.typewriter_log(
                    "SYSTEM: ", Fore.YELLOW, "无法执行命令"
                )
