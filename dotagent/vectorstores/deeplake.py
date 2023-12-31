"""Wrapper around Activeloop Deep Lake."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import numpy as np

try:
    import deeplake
    from deeplake.core.fast_forwarding import version_compare
    from deeplake.core.vectorstore import DeepLakeVectorStore

    _DEEPLAKE_INSTALLED = True
except ImportError:
    _DEEPLAKE_INSTALLED = False

from dotagent.schema import Document
from dotagent.vectorstores.embeddings.base import Embeddings
from dotagent.vectorstores.base import VectorStore
# from dotagent.vectorstores.utils import maximal_marginal_relevance

logger = logging.getLogger(__name__)

DEFAULT_DATASET_PATH = "./deeplake/"

class DeepLake(VectorStore):
    """Wrapper around Deep Lake, a data lake for deep learning applications.

    To use, you should have the ``deeplake`` python package installed.

    Example:
        .. code-block:: python

                from dotagent.vectorstores import DeepLake
                from dotagent.embeddings.openai import OpenAIEmbeddings

                embeddings = OpenAIEmbeddings()
                vectorstore = DeepLake("dotagent_db_path", embeddings.embed_query)
    """

    def __init__(
        self,
        dataset_path: str = DEFAULT_DATASET_PATH,
        token: Optional[str] = None,
        embedding_function: Optional[Embeddings] = None,
        read_only: bool = False,
        ingestion_batch_size: int = 1000,
        num_workers: int = 0,
        verbose: bool = True,
        exec_option: str = "python",
        **kwargs: Any,
    ) -> None:
        """Creates an empty DeepLakeVectorStore or loads an existing one.

        The DeepLakeVectorStore is located at the specified ``path``.

        Examples:
            >>> # Create a vector store with default tensors
            >>> deeplake_vectorstore = DeepLake(
            ...        path = <path_for_storing_Data>,
            ... )
            >>>
            >>> # Create a vector store in the Deep Lake Managed Tensor Database
            >>> data = DeepLake(
            ...        path = "hub://org_id/dataset_name",
            ...        exec_option = "tensor_db",
            ... )

        Args:
            dataset_path (str): Path to existing dataset or where to create
                a new one. Defaults to DEFAULT_DATASET_PATH
            token (str, optional):  Activeloop token, for fetching credentials
                to the dataset at path if it is a Deep Lake dataset.
                Tokens are normally autogenerated. Optional.
            embedding_function (str, optional): Function to convert
                either documents or query. Optional.
            read_only (bool): Open dataset in read-only mode. Default is False.
            ingestion_batch_size (int): During data ingestion, data is divided
                into batches. Batch size is the size of each batch.
                Default is 1000.
            num_workers (int): Number of workers to use during data ingestion.
                Default is 0.
            verbose (bool): Print dataset summary after each operation.
                Default is True.
            exec_option (str): DeepLakeVectorStore supports 3 ways to perform
                searching - "python", "compute_engine", "tensor_db".
                Default is "python".
                - ``python`` - Pure-python implementation that runs on the client.
                WARNING: using this with big datasets can lead to memory
                issues. Data can be stored anywhere.
                - ``compute_engine`` - C++ implementation of the Deep Lake Compute
                Engine that runs on the client. Can be used for any data stored in
                or connected to Deep Lake. Not for in-memory or local datasets.
                - ``tensor_db`` - Hosted Managed Tensor Database that is
                responsible for storage and query execution. Only for data stored in
                the Deep Lake Managed Database. Use runtime = {"db_engine": True} during
                dataset creation.
            **kwargs: Other optional keyword arguments.

        Raises:
            ValueError: If some condition is not met.
        """

        self.ingestion_batch_size = ingestion_batch_size
        self.num_workers = num_workers
        self.verbose = verbose

        if _DEEPLAKE_INSTALLED is False:
            raise ValueError(
                "Could not import deeplake python package. "
                "Please install it with `pip install deeplake`."
            )

        if version_compare(deeplake.__version__, "3.6.2") == -1:
            raise ValueError(
                "deeplake version should be >= 3.6.3, but you've installed"
                f" {deeplake.__version__}. Consider upgrading deeplake version \
                    pip install --upgrade deeplake."
            )
        self.dataset_path = dataset_path

        self.vectorstore = DeepLakeVectorStore(
            path=self.dataset_path,
            embedding_function=embedding_function,
            read_only=read_only,
            token=token,
            exec_option=exec_option,
            verbose=verbose,
            **kwargs,
        )

        self._embedding_function = embedding_function
        self._id_tensor_name = "ids" if "ids" in self.vectorstore.tensors() else "id"

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[dict]] = None,
        ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Run more texts through the embeddings and add to the vectorstore.

        Examples:
            >>> ids = deeplake_vectorstore.add_texts(
            ...     texts = <list_of_texts>,
            ...     metadatas = <list_of_metadata_jsons>,
            ...     ids = <list_of_ids>,
            ... )

        Args:
            texts (Iterable[str]): Texts to add to the vectorstore.
            metadatas (Optional[List[dict]], optional): Optional list of metadatas.
            ids (Optional[List[str]], optional): Optional list of IDs.
            **kwargs: other optional keyword arguments.

        Returns:
            List[str]: List of IDs of the added texts.
        """
        kwargs = {}
        if ids:
            if self._id_tensor_name == "ids":  # for backwards compatibility
                kwargs["ids"] = ids
            else:
                kwargs["id"] = ids

        if metadatas is None:
            metadatas = [{}] * len(list(texts))

        return self.vectorstore.add(
            text=texts,
            metadata=metadatas,
            embedding_data=texts,
            embedding_tensor="embedding",
            embedding_function=kwargs.get("embedding_function")
            or self._embedding_function.embed_documents,  # type: ignore
            return_ids=True,
            **kwargs,
        )

    def _search_tql(
        self,
        tql_query: Optional[str],
        exec_option: Optional[str] = None,
        return_score: bool = False,
    ) -> Any[List[Document], List[Tuple[Document, float]]]:
        """Function for performing tql_search.

        Args:
            tql_query (str): TQL Query string for direct evaluation.
                Available only for `compute_engine` and `tensor_db`.
            exec_option (str, optional): Supports 3 ways to search.
                Could be "python", "compute_engine" or "tensor_db". Default is "python".
                - ``python`` - Pure-python implementation for the client.
                    WARNING: not recommended for big datasets due to potential memory
                    issues.
                - ``compute_engine`` - C++ implementation of Deep Lake Compute
                    Engine for the client. Not for in-memory or local datasets.
                - ``tensor_db`` - Hosted Managed Tensor Database for storage
                    and query execution. Only for data in Deep Lake Managed Database.
                        Use runtime = {"db_engine": True} during dataset creation.
            return_score (bool): Return score with document. Default is False.

        Returns:
            List[Document] - A list of documents

        Raises:
            ValueError: If return_score is True but some condition is not met.
        """
        result = self.vectorstore.search(
            query=tql_query,
            exec_option=exec_option,
        )
        metadatas = result["metadata"]
        texts = result["text"]

        docs = [
            Document(
                page_content=text,
                metadata=metadata,
            )
            for text, metadata in zip(texts, metadatas)
        ]

        if return_score:
            raise ValueError("scores can't be returned with tql search")

        return docs

    def _search(
        self,
        query: Optional[str] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
        embedding_function: Optional[Callable] = None,
        k: int = 4,
        distance_metric: str = "L2",
        filter: Optional[Union[Dict, Callable]] = None,
        return_score: bool = True,
        exec_option: Optional[str] = None,
        **kwargs: Any,
    ) -> Any[List[Document], List[Tuple[Document, float]]]:
        """
        Return docs similar to query.

        Args:
            query (str, optional): Text to look up similar docs.
            embedding (Union[List[float], np.ndarray], optional): Query's embedding.
            embedding_function (Callable, optional): Function to convert `query`
                into embedding.
            k (int): Number of Documents to return.
            distance_metric (str): `L2` for Euclidean, `L1` for Nuclear, `max`
                for L-infinity distance, `cos` for cosine similarity, 'dot' for dot
                product.
            filter (Union[Dict, Callable], optional): Additional filter prior
                to the embedding search.
                - ``Dict`` - Key-value search on tensors of htype json, on an
                    AND basis (a sample must satisfy all key-value filters to be True)
                    Dict = {"tensor_name_1": {"key": value},
                            "tensor_name_2": {"key": value}}
                - ``Function`` - Any function compatible with `deeplake.filter`.
            use_maximal_marginal_relevance (bool): Use maximal marginal relevance.
            fetch_k (int): Number of Documents for MMR algorithm.
            return_score (bool): Return the score.
            exec_option (str, optional): Supports 3 ways to perform searching.
                Could be "python", "compute_engine" or "tensor_db".
                - ``python`` - Pure-python implementation for the client.
                    WARNING: not recommended for big datasets.
                - ``compute_engine`` - C++ implementation of Deep Lake Compute
                    Engine for the client. Not for in-memory or local datasets.
                - ``tensor_db`` - Hosted Managed Tensor Database for storage
                    and query execution. Only for data in Deep Lake Managed Database.
                    Use runtime = {"db_engine": True} during dataset creation.
            **kwargs: Additional keyword arguments.

        Returns:
            List of Documents by the specified distance metric,
            if return_score True, return a tuple of (Document, score)

        Raises:
            ValueError: if both `embedding` and `embedding_function` are not specified.
        """

        if kwargs.get("tql_query"):
            return self._search_tql(
                tql_query=kwargs["tql_query"],
                exec_option=exec_option,
                return_score=return_score,
            )

        if embedding_function:
            if isinstance(embedding_function, Embeddings):
                _embedding_function = embedding_function.embed_query
            else:
                _embedding_function = embedding_function
        elif self._embedding_function:
            _embedding_function = self._embedding_function.embed_query
        else:
            _embedding_function = None

        if embedding is None:
            if _embedding_function is None:
                raise ValueError(
                    "Either `embedding` or `embedding_function` needs to be specified."
                )

            embedding = _embedding_function(query) if query else None

        if isinstance(embedding, list):
            embedding = np.array(embedding, dtype=np.float32)
            if len(embedding.shape) > 1:
                embedding = embedding[0]

        result = self.vectorstore.search(
            embedding=embedding,
            k=k,
            distance_metric=distance_metric,
            filter=filter,
            exec_option=exec_option,
            return_tensors=["embedding", "metadata", "text"],
        )

        scores = result["score"]
        embeddings = result["embedding"]
        metadatas = result["metadata"]
        texts = result["text"]


        for meta, embed in zip(metadatas, embeddings):
            meta['embedding'] = embed
            metadatas.append(meta)

        docs = [
            Document(
                page_content=text,
                metadata=metadata,
            )
            for text, metadata in zip(texts, metadatas)
        ]

        if return_score:
            return [(doc, score) for doc, score in zip(docs, scores)]

        return docs

    def similarity_search(
        self,
        query: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        k: int = 4,
        **kwargs: Any,
    ) -> List[Document]:
        """
        Return docs most similar to query.

        Examples:
            >>> # Search using an embedding
            >>> data = vector_store.similarity_search(
            ...     query=<your_query>,
            ...     k=<num_items>,
            ...     exec_option=<preferred_exec_option>,
            ... )
            >>> # Run tql search:
            >>> data = vector_store.tql_search(
            ...     tql_query="SELECT * WHERE id == <id>",
            ...     exec_option="compute_engine",
            ... )
        """
        if (embedding is None and query is None) or (embedding is not None and query is not None):
            raise ValueError("You must provide either query embeddings or query texts, but not both")


        return self._search(
            query=query,
            embedding=embedding,
            k=k,
            **kwargs,
        )


    @classmethod
    def from_texts(
        cls,
        texts: List[str],
        embedding_function: Optional[Embeddings] = None,
        metadatas: Optional[List[dict]] = None,
        ids: Optional[List[str]] = None,
        dataset_path: str = DEFAULT_DATASET_PATH,
        **kwargs: Any,
    ) -> DeepLake:
        """Create a Deep Lake dataset from a raw documents.

        If a dataset_path is specified, the dataset will be persisted in that location,
        otherwise by default at `./deeplake`

        Examples:
        >>> # Search using an embedding
        >>> vector_store = DeepLake.from_texts(
        ...        texts = <the_texts_that_you_want_to_embed>,
        ...        embedding_function = <embedding_function_for_query>,
        ...        k = <number_of_items_to_return>,
        ...        exec_option = <preferred_exec_option>,
        ... )

        """
        
        if kwargs.get("embedding"):
            raise ValueError(
                "using embedding as embedidng_functions is deprecated. "
                "Please use `embedding_function` instead."
            )

        deeplake_dataset = cls(
            dataset_path=dataset_path, embedding_function=embedding_function, **kwargs
        )
        deeplake_dataset.add_texts(
            texts=texts,
            metadatas=metadatas,
            ids=ids,
            embedding_function=embedding.embed_documents,  # type: ignore
        )
        return deeplake_dataset

    def delete(
        self,
        ids: Any[List[str], None] = None,
        filter: Any[Dict[str, str], None] = None,
        delete_all: Any[bool, None] = None,
    ) -> bool:
        """Delete the entities in the dataset.

        Args:
            ids (Optional[List[str]], optional): The document_ids to delete.
                Defaults to None.
            filter (Optional[Dict[str, str]], optional): The filter to delete by.
                Defaults to None.
            delete_all (Optional[bool], optional): Whether to drop the dataset.
                Defaults to None.

        Returns:
            bool: Whether the delete operation was successful.
        """
        self.vectorstore.delete(
            ids=ids,
            filter=filter,
            delete_all=delete_all,
        )

        return True

    @classmethod
    def force_delete_by_path(cls, path: str) -> None:
        """Force delete dataset by path.

        Args:
            path (str): path of the dataset to delete.

        Raises:
            ValueError: if deeplake is not installed.
        """

        try:
            import deeplake
        except ImportError:
            raise ValueError(
                "Could not import deeplake python package. "
                "Please install it with `pip install deeplake`."
            )
        deeplake.delete(path, large_ok=True, force=True)

    def delete_dataset(self) -> None:
        """Delete the collection."""
        self.delete(delete_all=True)
