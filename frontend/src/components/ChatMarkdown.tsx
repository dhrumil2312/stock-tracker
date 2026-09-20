import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  text: string;
}

export default function ChatMarkdown({ text }: Props) {
  return (
    <div className="chat-md">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          img: () => null,
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
